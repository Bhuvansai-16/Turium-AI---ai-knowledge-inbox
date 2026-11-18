import sqlite3

import pytest

from app.config import get_settings
from app.services.retrieval import keyword_query

INVOICE = "Invoice INV-20931 from Northwind is overdue by 30 days."
ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."


@pytest.fixture
def strict_floor(settings_env):
    """A similarity floor so high that only keyword matches can get through."""
    settings_env.setenv("MIN_SCORE", "0.99")
    get_settings.cache_clear()


def ask(client, question: str) -> dict:
    return client.post("/query", json={"question": question}).json()


def test_keyword_query_drops_stopwords_and_quotes_terms():
    assert keyword_query("What about INV-20931?") == '("inv" AND "20931")'


def test_keyword_query_with_only_stopwords_is_none():
    assert keyword_query("what is the") is None


def test_exact_keyword_match_passes_the_similarity_floor(client, strict_floor):
    invoice_id = client.post("/ingest", json={"type": "note", "content": INVOICE}).json()["id"]
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    body = ask(client, "Status of INV-20931?")

    assert [source["item_id"] for source in body["sources"]] == [invoice_id]


def test_unrelated_question_still_finds_nothing(client, strict_floor):
    client.post("/ingest", json={"type": "note", "content": INVOICE})

    body = ask(client, "Recipe for carbonara?")

    assert body["sources"] == []
    assert body["answer"] == "I couldn't find that in your saved items."


def test_deleted_item_leaves_the_keyword_index(client, strict_floor):
    invoice_id = client.post("/ingest", json={"type": "note", "content": INVOICE}).json()["id"]
    client.delete(f"/items/{invoice_id}")
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    assert ask(client, "Status of INV-20931?")["sources"] == []


def test_existing_chunks_are_indexed_when_the_keyword_index_is_added(settings_env, tmp_path):
    from app import db, repository

    with sqlite3.connect(tmp_path / "test.db") as conn:
        conn.executescript(
            """
            CREATE TABLE items (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, title TEXT NOT NULL, url TEXT UNIQUE,
              raw_content TEXT NOT NULL DEFAULT '', content_hash TEXT, status TEXT NOT NULL, error TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, position INTEGER NOT NULL,
              text TEXT NOT NULL, embedding BLOB NOT NULL, embedding_model TEXT NOT NULL);
            INSERT INTO items VALUES ('a', 'note', 'Invoice', NULL, 'x', 'h', 'ready', NULL, 't', 't');
            INSERT INTO chunks (item_id, position, text, embedding, embedding_model)
              VALUES ('a', 0, 'Invoice INV-20931 is overdue', x'00', 'fake-embed');
            """
        )

    db.init_db()

    with db.connect() as conn:
        assert repository.keyword_search(conn, '"20931"', "fake-embed", 10) == [1]


def test_item_found_by_its_title_and_kind(client, strict_floor):
    # People name items by what they are, not what they say: "the md file I uploaded".
    roadmap = "Launch the citation viewer in August and the Slack connector in September."
    files = {"file": ("q3-roadmap.md", roadmap.encode(), "text/markdown")}
    file_id = client.post("/ingest/file", files=files).json()["id"]
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    body = ask(client, "the md file i uploaded, whats in it")

    assert [source["item_id"] for source in body["sources"]] == [file_id]


def test_keyword_search_matches_word_forms(client, strict_floor):
    note_id = client.post("/ingest", json={"type": "note", "content": "Offsite note: the team meets in Lisbon."}).json()["id"]

    body = ask(client, "what are my notes on offsites")

    assert [source["item_id"] for source in body["sources"]] == [note_id]


def test_keyword_index_from_earlier_version_is_rebuilt(client):
    from app import db, repository

    client.post("/ingest", json={"type": "note", "content": INVOICE})
    with db.connect() as conn:  # the earlier index: chunk text only, no stemming
        conn.executescript(
            "DROP TRIGGER chunks_fts_insert; DROP TRIGGER chunks_fts_delete; DROP TABLE chunks_fts;"
            "CREATE VIRTUAL TABLE chunks_fts USING fts5(text, content='chunks', content_rowid='id');"
        )

    db.init_db()

    with db.connect() as conn:
        assert "porter" in conn.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'").fetchone()[0]
        assert repository.keyword_search(conn, '"northwind"', "fake-embed", 10)
