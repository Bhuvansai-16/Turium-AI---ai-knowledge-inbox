"""Edge cases: races with background work, half-saved chats, and loose keyword matches."""

import pytest

from app import db, repository
from app.config import get_settings
from app.errors import AppError
from app.services import conversations
from app.services.retrieval import keyword_query

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."
POLICY = "Expense policy: meals are reimbursed up to 40 euros per day with a receipt."


@pytest.fixture(autouse=True)
def low_threshold(settings_env):
    settings_env.setenv("MIN_SCORE", "0.1")
    get_settings.cache_clear()


def test_keyword_search_needs_two_shared_words():
    # One shared word ("policy") is not enough to bypass the relevance floor.
    assert keyword_query("What is our vacation policy?") == '("vacation" AND "policy")'
    assert keyword_query("Status of INV-20931?") == '("status" AND "inv") OR ("status" AND "20931") OR ("inv" AND "20931")'
    assert keyword_query("Northwind?") == '"northwind"'


def test_one_shared_word_does_not_count_as_relevant(client, settings_env):
    settings_env.setenv("MIN_SCORE", "0.99")
    get_settings.cache_clear()
    client.post("/ingest", json={"type": "note", "content": POLICY})

    body = client.post("/query", json={"question": "What is our vacation policy?"}).json()

    assert body["sources"] == []
    assert body["meta"]["retrieved"] == 0


def test_chunk_indexed_between_reads_is_skipped(client, monkeypatch):
    # Background ingestion can commit a chunk after vectors are loaded but before the keyword
    # search runs; that chunk has no vector score yet and must not crash the query.
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    real = repository.keyword_search
    monkeypatch.setattr(repository, "keyword_search", lambda *args: [999_999, *real(*args)])

    response = client.post("/query", json={"question": "What does Turium build with Zebra?"})

    assert response.status_code == 200
    assert response.json()["sources"]


def test_history_survives_a_question_without_answer(client):
    with db.connect() as conn:
        thread_id = repository.create_thread(conn, "Zebra")
        repository.add_message(conn, thread_id, "user", "lost question")  # server restarted mid-answer
        repository.add_message(conn, thread_id, "user", "What is Zebra?")
        repository.add_message(conn, thread_id, "assistant", "Zebra answers questions [1].")

    assert conversations.history(thread_id) == [("What is Zebra?", "Zebra answers questions [1].")]


def test_thread_deleted_mid_request_is_404_not_500(client):
    with pytest.raises(AppError) as err:
        conversations.start_turn("deleted-thread", "Does it cite sources?")

    assert err.value.status == 404
