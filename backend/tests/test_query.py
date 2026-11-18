import pytest

from app import db, repository
from app.config import get_settings
from app.services.llm import get_llm
from tests.fakes import FakeLLM

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."
PASTA = "Carbonara uses eggs, pecorino, guanciale and black pepper."


@pytest.fixture(autouse=True)
def low_threshold(settings_env):
    # The fake bag-of-words embeddings score lower than real models, so loosen the cutoff.
    settings_env.setenv("MIN_SCORE", "0.1")
    get_settings.cache_clear()


def ingest(client, content: str) -> str:
    return client.post("/ingest", json={"type": "note", "content": content}).json()["id"]


def ask(client, question: str, **extra):
    return client.post("/query", json={"question": question, **extra})


def test_query_returns_cited_source(client, fake_llm):
    zebra_id = ingest(client, ZEBRA)
    ingest(client, PASTA)

    response = ask(client, "What does Turium build with Zebra?")

    assert response.status_code == 200
    body = response.json()
    assert "[1]" in body["answer"]
    assert body["sources"][0]["ref"] == 1
    assert body["sources"][0]["item_id"] == zebra_id
    assert "Zebra" in body["sources"][0]["snippet"]
    assert body["meta"]["model"] == "fake-chat"
    assert body["meta"]["retrieved"] >= 1
    assert len(fake_llm.calls) == 1


def test_only_cited_sources_returned(client, fake_llm):
    ingest(client, ZEBRA)
    ingest(client, "Zebra pricing is per seat for enterprise customers.")
    fake_llm.answer = "Zebra is sold per seat [2]."

    body = ask(client, "How is Zebra priced for enterprise?").json()

    assert [s["ref"] for s in body["sources"]] == [2]


def test_empty_inbox_no_llm_call(client, fake_llm):
    body = ask(client, "What does Turium build?").json()

    assert body["answer"] == "Your inbox is empty. Add a note or URL first."
    assert body["sources"] == []
    assert fake_llm.calls == []


def test_items_processing_message(client, fake_llm):
    with db.connect() as conn:
        repository.create_item(
            conn, source_type="note", title="t", url=None, raw_content="pending text", content_hash="h"
        )

    body = ask(client, "What does Turium build?").json()

    assert body["answer"] == "Your items are still processing. Try again in a moment."
    assert fake_llm.calls == []


def test_irrelevant_question_not_found(client, fake_llm):
    ingest(client, ZEBRA)

    body = ask(client, "Recipe carbonara pecorino?").json()

    assert body["answer"] == "I couldn't find that in your saved items."
    assert body["sources"] == []
    assert fake_llm.calls == []


def test_falls_back_to_all_sources_when_no_citation(client, fake_llm):
    ingest(client, ZEBRA)
    fake_llm.answer = "Turium builds Zebra."

    body = ask(client, "What does Turium build with Zebra?").json()

    assert len(body["sources"]) == body["meta"]["retrieved"]


def test_model_refusal_returns_no_sources(client, fake_llm):
    ingest(client, ZEBRA)
    fake_llm.answer = "I couldn't find that in your saved items."

    body = ask(client, "What does Turium build with Zebra?").json()

    assert body["sources"] == []


def test_provider_failure_502(client):
    ingest(client, ZEBRA)
    client.app.dependency_overrides[get_llm] = lambda: FakeLLM(fail=True)

    response = ask(client, "What does Turium build?")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_short_question_422(client):
    assert ask(client, "hi").status_code == 422


def test_top_k_out_of_range_422(client):
    assert ask(client, "What does Turium build?", top_k=50).status_code == 422


def test_query_without_provider_503(unconfigured_client):
    response = ask(unconfigured_client, "What does Turium build?")

    assert response.status_code == 503
