import json

import pytest

from app.config import get_settings

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."


@pytest.fixture(autouse=True)
def low_threshold(settings_env):
    settings_env.setenv("MIN_SCORE", "0.1")
    get_settings.cache_clear()


def events(response) -> list[tuple[str, dict]]:
    parsed = []
    for block in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        parsed.append((fields["event"], json.loads(fields["data"])))
    return parsed


def ask(client, question: str, thread_id: str | None = None):
    body = {"question": question, **({"thread_id": thread_id} if thread_id else {})}
    return client.post("/query/stream", json=body)


def test_new_question_starts_a_thread(client):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    parsed = events(ask(client, "What does Turium build with Zebra?"))

    name, data = parsed[0]
    assert name == "thread"
    thread = client.get(f"/threads/{data['id']}").json()
    assert thread["title"] == "What does Turium build with Zebra?"
    assert [m["role"] for m in thread["messages"]] == ["user", "assistant"]
    assistant = thread["messages"][1]
    assert assistant["content"] == "Answer from notes [1]."
    assert assistant["status"] == "done"
    assert assistant["sources"][0]["ref"] == 1
    assert assistant["meta"]["model"] == "fake-chat"


def test_follow_up_question_continues_the_thread(client):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    thread_id = events(ask(client, "What does Turium build with Zebra?"))[0][1]["id"]

    parsed = events(ask(client, "Does Zebra cite sources?", thread_id))

    assert parsed[0] == ("thread", {"id": thread_id, "title": "What does Turium build with Zebra?"})
    messages = client.get(f"/threads/{thread_id}").json()["messages"]
    assert [m["content"] for m in messages if m["role"] == "user"] == [
        "What does Turium build with Zebra?",
        "Does Zebra cite sources?",
    ]


def test_threads_listed_most_recent_first(client):
    first = events(ask(client, "First question here?"))[0][1]["id"]
    second = events(ask(client, "Second question here?"))[0][1]["id"]
    ask(client, "Back to the first one?", first)

    threads = client.get("/threads").json()["threads"]

    assert [t["id"] for t in threads] == [first, second]


def test_answer_without_llm_is_saved_too(client):
    thread_id = events(ask(client, "What does Turium build?"))[0][1]["id"]

    assistant = client.get(f"/threads/{thread_id}").json()["messages"][1]

    assert assistant["content"] == "Your inbox is empty. Add a note or URL first."
    assert assistant["sources"] == []


def test_provider_failure_mid_answer_saves_partial_as_error(client, fake_llm):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    fake_llm.fail_mid_stream = True

    thread_id = events(ask(client, "What does Turium build with Zebra?"))[0][1]["id"]

    assistant = client.get(f"/threads/{thread_id}").json()["messages"][1]
    assert assistant["status"] == "error"
    assert assistant["content"] == "Answer"


def test_stopped_answer_keeps_partial_text(client):
    from app.services import conversations

    thread_id, _ = conversations.start_turn(None, "Long question that gets stopped?")
    stream = conversations.record_answer(thread_id, iter([("token", {"text": "Partial "}), ("token", {"text": "answer"})]))

    next(stream)
    stream.close()  # what happens when the browser disconnects (Stop)

    assistant = client.get(f"/threads/{thread_id}").json()["messages"][1]
    assert assistant["status"] == "stopped"
    assert assistant["content"] == "Partial"


def test_unknown_thread_404(client):
    response = ask(client, "What does Turium build?", "missing-thread")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "thread_not_found"


def test_delete_thread(client):
    thread_id = events(ask(client, "What does Turium build?"))[0][1]["id"]

    assert client.delete(f"/threads/{thread_id}").status_code == 204
    assert client.get(f"/threads/{thread_id}").status_code == 404
    assert client.get("/threads").json()["threads"] == []


def test_delete_unknown_thread_404(client):
    assert client.delete("/threads/nope").status_code == 404
