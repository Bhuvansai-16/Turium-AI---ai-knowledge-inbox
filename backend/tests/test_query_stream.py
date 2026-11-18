import json

import pytest

from app.config import get_settings
from app.services.llm import get_llm
from tests.fakes import FakeLLM

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."


@pytest.fixture(autouse=True)
def low_threshold(settings_env):
    settings_env.setenv("MIN_SCORE", "0.1")
    get_settings.cache_clear()


def ingest(client, content: str = ZEBRA) -> str:
    return client.post("/ingest", json={"type": "note", "content": content}).json()["id"]


def stream(client, question: str):
    return client.post("/query/stream", json={"question": question})


def events(response) -> list[tuple[str, dict]]:
    """Parse a Server-Sent Events body into (event, data) pairs, skipping the leading `thread`
    event (chat history has its own tests in test_threads.py)."""
    parsed = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((fields["event"], json.loads(fields["data"])))
    return [event for event in parsed if event[0] != "thread"]


def test_stream_sends_sources_tokens_then_done(client):
    item_id = ingest(client)

    response = stream(client, "What does Turium build with Zebra?")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    parsed = events(response)
    names = [name for name, _ in parsed]
    assert names[0] == "sources"
    assert names[-1] == "done"
    assert set(names[1:-1]) == {"token"}

    sources = parsed[0][1]["sources"]
    assert sources[0]["ref"] == 1
    assert sources[0]["item_id"] == item_id

    streamed = "".join(data["text"] for name, data in parsed if name == "token")
    done = parsed[-1][1]
    assert streamed == done["answer"] == "Answer from notes [1]."
    assert [s["ref"] for s in done["sources"]] == [1]
    assert done["meta"]["model"] == "fake-chat"


def test_stream_empty_inbox_is_single_done_event(client, fake_llm):
    parsed = events(stream(client, "What does Turium build?"))

    assert parsed == [("done", parsed[0][1])]
    assert parsed[0][1]["answer"] == "Your inbox is empty. Add a note or URL first."
    assert fake_llm.calls == []


def test_stream_not_found_skips_llm(client, fake_llm):
    ingest(client)

    parsed = events(stream(client, "Recipe carbonara pecorino?"))

    assert [name for name, _ in parsed] == ["done"]
    assert parsed[0][1]["answer"] == "I couldn't find that in your saved items."
    assert fake_llm.calls == []


def test_stream_retrieval_failure_is_plain_502(client):
    ingest(client)
    client.app.dependency_overrides[get_llm] = lambda: FakeLLM(fail=True)

    response = stream(client, "What does Turium build?")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "upstream_error"


def test_stream_failure_mid_answer_sends_error_event(client, fake_llm):
    ingest(client)
    fake_llm.fail_mid_stream = True

    parsed = events(stream(client, "What does Turium build with Zebra?"))

    assert [name for name, _ in parsed] == ["sources", "token", "error"]
    assert parsed[-1][1]["code"] == "upstream_error"


def test_stream_validates_question(client):
    assert stream(client, "hi").status_code == 422


def test_stream_without_provider_503(unconfigured_client):
    assert stream(unconfigured_client, "What does Turium build?").status_code == 503
