import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

ITEMS_COLUMNS = """
    id            TEXT PRIMARY KEY,
    source_type   TEXT NOT NULL CHECK (source_type IN ('note', 'url', 'file')),
    title         TEXT NOT NULL,
    url           TEXT UNIQUE,
    raw_content   TEXT NOT NULL DEFAULT '',
    content_hash  TEXT,
    status        TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    error         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
"""

def keyword_document(text: str) -> str:
    """SQL for what the keyword index stores per chunk: title, kind words, then the text."""
    kind = "CASE items.source_type WHEN 'url' THEN 'link web page' WHEN 'file' THEN 'file document' ELSE 'note' END"
    return f"items.title || ' ' || {kind} || ' ' || {text}"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS items ({ITEMS_COLUMNS});
CREATE INDEX IF NOT EXISTS idx_items_content_hash ON items (content_hash);

CREATE TABLE IF NOT EXISTS chunks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          TEXT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    text             TEXT NOT NULL,
    embedding        BLOB NOT NULL,
    embedding_model  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_item_id ON chunks (item_id);

-- Keyword index (BM25), kept in sync with chunks by triggers. Each chunk is indexed with its
-- item's title and kind, because people name items by what they are ("the md file I uploaded",
-- "the link I sent"), not only by what they say. Porter stemming lets "notes" match "note".
-- Deleting an item cascades to its chunks, which fires the delete trigger.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text)
    SELECT new.id, {keyword_document("new.text")} FROM items WHERE items.id = new.item_id;
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE rowid = old.id;
END;

CREATE TABLE IF NOT EXISTS threads (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL REFERENCES threads (id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'done' CHECK (status IN ('done', 'stopped', 'error')),
    sources     TEXT NOT NULL DEFAULT '[]',
    meta        TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages (thread_id, id);
"""


@contextmanager
def connect(path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Short-lived connection per unit of work: commits on success, rolls back on error, always closes.

    One connection per call keeps request threads and background ingestion threads independent.
    """
    conn = sqlite3.connect(path or get_settings().db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    db_path = Path(get_settings().db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(str(db_path)) as conn:
        _allow_file_items(conn)
        _drop_outdated_keyword_index(conn)
        had_keyword_index = _table_exists(conn, "chunks_fts")
        conn.executescript(SCHEMA)
        if not had_keyword_index:
            # Existing chunks (older database, or the index was rebuilt): index them once.
            conn.execute(
                f"""INSERT INTO chunks_fts (rowid, text)
                    SELECT chunks.id, {keyword_document("chunks.text")} FROM chunks JOIN items ON items.id = chunks.item_id"""
            )


def _drop_outdated_keyword_index(conn: sqlite3.Connection) -> None:
    """An index built by an earlier version (text only, no stemming) is dropped and rebuilt."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'").fetchone()
    if row and "porter" not in row[0]:
        conn.executescript(
            "DROP TRIGGER IF EXISTS chunks_fts_insert; DROP TRIGGER IF EXISTS chunks_fts_delete; DROP TABLE chunks_fts;"
        )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None


def _allow_file_items(conn: sqlite3.Connection) -> None:
    """Migrate databases created before file uploads, whose CHECK constraint only allowed
    'note' and 'url'. SQLite can't alter a CHECK, so the table is rebuilt (the documented
    create-copy-drop-rename procedure, with foreign keys off so chunks are untouched)."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'items'").fetchone()
    if row is None or "'file'" in row["sql"]:
        return
    conn.executescript(
        f"""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        CREATE TABLE items_new ({ITEMS_COLUMNS});
        INSERT INTO items_new SELECT * FROM items;
        DROP TABLE items;
        ALTER TABLE items_new RENAME TO items;
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )
