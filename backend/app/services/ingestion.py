"""Ingestion: accept an item synchronously, then fetch -> chunk -> embed -> store in the background.

The request only validates, dedupes and inserts a `pending` row, so POST /ingest returns
in milliseconds regardless of how slow the URL or the embedding provider is. The client
polls GET /items to watch the status move pending -> processing -> ready | failed.
"""

import hashlib
import sqlite3
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from urllib.parse import urlsplit, urlunsplit

import structlog

from app import db, repository
from app.errors import AppError
from app.schemas import NoteIn, UrlIn
from app.services.chunker import SENTENCE_END, chunk_text
from app.services.fetcher import FetchError, fetch_url
from app.services.llm import LLMClient, ProviderError

NOTE_TITLE_CHARS = 60

log = structlog.get_logger()


class DuplicateItemError(Exception):
    def __init__(self, existing_id: str):
        super().__init__(existing_id)
        self.existing_id = existing_id


class IngestionError(Exception):
    """Expected failure; the message is shown to the user on the item."""


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))


def note_title(content: str) -> str:
    """A short, readable title for an untitled note: the first line if it's short, else a
    leading "Label:" if there is one, else the first sentence, else a cut at a word with "…"."""
    first_line = content.strip().splitlines()[0].strip()
    if len(first_line) <= NOTE_TITLE_CHARS:
        return first_line

    label, colon, _ = first_line.partition(": ")
    if colon and len(label) <= NOTE_TITLE_CHARS // 2:
        return label

    sentence = SENTENCE_END.split(first_line, maxsplit=1)[0].rstrip(".!?")
    if len(sentence) <= NOTE_TITLE_CHARS:
        return sentence

    return first_line[:NOTE_TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def content_hash(content: str) -> str:
    return hashlib.sha256(" ".join(content.split()).encode()).hexdigest()


def submit(conn, request: NoteIn | UrlIn) -> str:
    """Insert a pending item, or re-queue a failed duplicate. Raises DuplicateItemError otherwise."""
    if isinstance(request, NoteIn):
        url, digest = None, content_hash(request.content)
        fields = dict(source_type="note", title=request.title or note_title(request.content), raw_content=request.content)
    else:
        url, digest = normalize_url(str(request.url)), None
        fields = dict(source_type="url", title=urlsplit(url).hostname or url, raw_content="")
    return _insert_or_requeue(conn, url, digest, fields)


def submit_file(conn, filename: str, text: str) -> str:
    """Uploaded files are stored as their extracted text and deduplicated by content, like notes."""
    fields = dict(source_type="file", title=filename, raw_content=text)
    return _insert_or_requeue(conn, None, content_hash(text), fields)


def _insert_or_requeue(conn, url: str | None, digest: str | None, fields: dict) -> str:
    existing = repository.find_duplicate(conn, url=url, content_hash=digest)
    if existing is not None:
        if existing["status"] != "failed":
            raise DuplicateItemError(existing["id"])
        repository.reset_for_retry(conn, existing["id"])
        return existing["id"]

    try:
        return repository.create_item(conn, url=url, content_hash=digest, **fields)
    except sqlite3.IntegrityError:
        # A concurrent request inserted the same URL between our check and insert.
        winner = conn.execute("SELECT id FROM items WHERE url = ?", (url,)).fetchone()
        if winner is None:
            raise
        raise DuplicateItemError(winner["id"]) from None


def run_ingestion(item_id: str, llm: LLMClient) -> None:
    item_log = log.bind(item_id=item_id)
    try:
        with db.connect() as conn:
            item = repository.get_item(conn, item_id)
            if item is None:
                return
            repository.set_status(conn, item_id, "processing")

        text = item["raw_content"]
        # Only fetch pages we don't have yet; re-indexing and retries after an embedding
        # failure reuse the stored text instead of downloading the page again.
        if item["source_type"] == "url" and not text:
            with _stage(item_log, "fetch"):
                page = fetch_url(item["url"])
            text = page.text
            with db.connect() as conn:
                repository.set_content(conn, item_id, page.title or item["title"], text)

        with _stage(item_log, "chunk"):
            chunks = chunk_text(text)
        if not chunks:
            raise IngestionError("No readable text found at this URL")

        with _stage(item_log, "embed"):
            vectors = llm.embed(chunks)

        with db.connect() as conn:
            # The user may have deleted the item while we were fetching or embedding.
            if repository.get_item(conn, item_id) is None:
                item_log.info("ingest.item_deleted")
                return
            repository.replace_chunks(conn, item_id, chunks, vectors, llm.embed_model)
            repository.set_status(conn, item_id, "ready")
        item_log.info("ingest.completed", chunks=len(chunks))

    except (FetchError, IngestionError) as exc:
        _fail(item_log, item_id, str(exc))
    except ProviderError:
        _fail(item_log, item_id, "The AI provider failed while indexing this item. Add it again to retry.")
    except Exception:
        item_log.exception("ingest.unexpected_error")
        _fail(item_log, item_id, "Unexpected error while processing this item")


def requeue_stuck_items(get_client: Callable[[], LLMClient]) -> None:
    """Background tasks live in-process, so a restart loses them. On startup, resume anything
    left pending/processing on a daemon thread (so startup isn't blocked by the provider)."""
    with db.connect() as conn:
        item_ids = repository.stuck_item_ids(conn)
    if not item_ids:
        return

    try:
        llm = get_client()
    except AppError as exc:
        for item_id in item_ids:
            _fail(log.bind(item_id=item_id), item_id, exc.message)
        return

    log.info("ingest.requeued", count=len(item_ids))
    threading.Thread(
        target=lambda: [run_ingestion(item_id, llm) for item_id in item_ids],
        name="ingest-requeue",
        daemon=True,
    ).start()


def _fail(item_log, item_id: str, message: str) -> None:
    item_log.warning("ingest.failed", reason=message)
    with db.connect() as conn:
        repository.set_status(conn, item_id, "failed", message)


@contextmanager
def _stage(item_log, stage: str):
    started = time.perf_counter()
    yield
    item_log.info("ingest.stage", stage=stage, duration_ms=round((time.perf_counter() - started) * 1000, 1))
