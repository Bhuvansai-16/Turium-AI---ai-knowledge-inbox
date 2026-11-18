"""All SQL lives here. Functions take an open connection so callers control transactions."""

import json
import sqlite3
import uuid
from datetime import UTC, datetime

import numpy as np

ITEM_WITH_COUNT = """
SELECT items.*, (SELECT COUNT(*) FROM chunks WHERE chunks.item_id = items.id) AS chunk_count
FROM items
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def create_item(
    conn: sqlite3.Connection,
    *,
    source_type: str,
    title: str,
    url: str | None,
    raw_content: str,
    content_hash: str | None,
) -> str:
    item_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        """INSERT INTO items (id, source_type, title, url, raw_content, content_hash, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (item_id, source_type, title, url, raw_content, content_hash, now, now),
    )
    return item_id


def find_duplicate(conn: sqlite3.Connection, *, url: str | None, content_hash: str | None) -> sqlite3.Row | None:
    if url is not None:
        return conn.execute("SELECT id, status FROM items WHERE url = ?", (url,)).fetchone()
    return conn.execute("SELECT id, status FROM items WHERE content_hash = ?", (content_hash,)).fetchone()


def get_item(conn: sqlite3.Connection, item_id: str) -> sqlite3.Row | None:
    return conn.execute(f"{ITEM_WITH_COUNT} WHERE items.id = ?", (item_id,)).fetchone()


def list_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"{ITEM_WITH_COUNT} ORDER BY items.created_at DESC, items.rowid DESC").fetchall()


def set_status(conn: sqlite3.Connection, item_id: str, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE items SET status = ?, error = ?, updated_at = ? WHERE id = ?",
        (status, error, _now(), item_id),
    )


def delete_item(conn: sqlite3.Connection, item_id: str) -> bool:
    """Deletes the item; its chunks go with it via ON DELETE CASCADE."""
    return conn.execute("DELETE FROM items WHERE id = ?", (item_id,)).rowcount > 0


def reset_for_retry(conn: sqlite3.Connection, item_id: str) -> None:
    set_status(conn, item_id, "pending")


def set_content(conn: sqlite3.Connection, item_id: str, title: str, raw_content: str) -> None:
    conn.execute(
        "UPDATE items SET title = ?, raw_content = ?, updated_at = ? WHERE id = ?",
        (title, raw_content, _now(), item_id),
    )


def replace_chunks(
    conn: sqlite3.Connection, item_id: str, texts: list[str], vectors: np.ndarray, model: str
) -> None:
    conn.execute("DELETE FROM chunks WHERE item_id = ?", (item_id,))
    conn.executemany(
        "INSERT INTO chunks (item_id, position, text, embedding, embedding_model) VALUES (?, ?, ?, ?, ?)",
        [
            (item_id, position, text, vector.astype(np.float32).tobytes(), model)
            for position, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ],
    )


def count_items_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM items GROUP BY status").fetchall()
    return {row["status"]: row["n"] for row in rows}


def load_vectors(conn: sqlite3.Connection, model: str) -> tuple[list[int], np.ndarray]:
    """Chunk ids and their stacked vectors, for ready items embedded with `model` only."""
    rows = conn.execute(
        """SELECT chunks.id, chunks.embedding FROM chunks
           JOIN items ON items.id = chunks.item_id
           WHERE items.status = 'ready' AND chunks.embedding_model = ?""",
        (model,),
    ).fetchall()
    if not rows:
        return [], np.empty((0, 0), dtype=np.float32)
    return [row["id"] for row in rows], np.vstack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])


def keyword_search(conn: sqlite3.Connection, fts_query: str, model: str, limit: int) -> list[int]:
    """Chunk ids matching an FTS5 query, best BM25 match first (ready items, current model only)."""
    rows = conn.execute(
        """SELECT chunks.id FROM chunks_fts
           JOIN chunks ON chunks.id = chunks_fts.rowid
           JOIN items ON items.id = chunks.item_id
           WHERE chunks_fts MATCH ? AND items.status = 'ready' AND chunks.embedding_model = ?
           ORDER BY bm25(chunks_fts) LIMIT ?""",
        (fts_query, model, limit),
    ).fetchall()
    return [row["id"] for row in rows]


def opening_chunk_ids(conn: sqlite3.Connection, model: str, limit: int) -> list[int]:
    """The first chunk of each ready item, newest item first: a cheap summary of the library."""
    rows = conn.execute(
        """SELECT chunks.id FROM chunks JOIN items ON items.id = chunks.item_id
           WHERE chunks.position = 0 AND items.status = 'ready' AND chunks.embedding_model = ?
           ORDER BY items.created_at DESC LIMIT ?""",
        (model, limit),
    ).fetchall()
    return [row["id"] for row in rows]


def get_chunks(conn: sqlite3.Connection, chunk_ids: list[int]) -> list[sqlite3.Row]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    return conn.execute(
        f"""SELECT chunks.id, chunks.item_id, chunks.text, items.title, items.source_type, items.url
            FROM chunks JOIN items ON items.id = chunks.item_id
            WHERE chunks.id IN ({placeholders})""",
        chunk_ids,
    ).fetchall()


def create_thread(conn: sqlite3.Connection, title: str) -> str:
    thread_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        "INSERT INTO threads (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (thread_id, title, now, now),
    )
    return thread_id


def get_thread(conn: sqlite3.Connection, thread_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()


def list_threads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM threads ORDER BY updated_at DESC, rowid DESC").fetchall()


def delete_thread(conn: sqlite3.Connection, thread_id: str) -> bool:
    """Deletes the thread; its messages go with it via ON DELETE CASCADE."""
    return conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,)).rowcount > 0


def add_message(
    conn: sqlite3.Connection,
    thread_id: str,
    role: str,
    content: str,
    *,
    status: str = "done",
    sources: list[dict] | None = None,
    meta: dict | None = None,
) -> None:
    now = _now()
    conn.execute(
        """INSERT INTO messages (thread_id, role, content, status, sources, meta, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (thread_id, role, content, status, json.dumps(sources or []), json.dumps(meta) if meta else None, now),
    )
    # Bumping updated_at keeps the most recently used thread at the top of the history.
    conn.execute("UPDATE threads SET updated_at = ? WHERE id = ?", (now, thread_id))


def thread_messages(conn: sqlite3.Connection, thread_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id", (thread_id,)).fetchall()
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "status": row["status"],
            "sources": json.loads(row["sources"]),
            "meta": json.loads(row["meta"]) if row["meta"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def all_item_ids(conn: sqlite3.Connection) -> list[str]:
    return [row["id"] for row in conn.execute("SELECT id FROM items ORDER BY created_at").fetchall()]


def stuck_item_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT id FROM items WHERE status IN ('pending', 'processing')").fetchall()
    return [row["id"] for row in rows]
