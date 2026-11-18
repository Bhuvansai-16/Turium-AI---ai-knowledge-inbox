import json

import pytest

from app.config import get_settings

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."
PASTA = "Carbonara uses eggs, pecorino, guanciale and black pepper."


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


def ask(client, question: str, thread_id: str | None = None) -> list[tuple[str, dict]]:
    body = {"question": question, **({"thread_id": thread_id} if thread_id else {})}
    return events(client.post("/query/stream", json=body))


def done(parsed) -> dict:
    return next(data for name, data in parsed if name == "done")


def test_first_question_is_used_as_is(client, fake_llm):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    parsed = ask(client, "What does Turium build with Zebra?")

    assert fake_llm.rewrites == []
    assert done(parsed)["meta"]["search_query"] is None


def test_follow_up_is_rewritten_using_the_chat(client, fake_llm):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    client.post("/ingest", json={"type": "note", "content": PASTA})
    thread_id = ask(client, "What does Turium build with Zebra?")[0][1]["id"]
    fake_llm.rewritten = "Does Zebra cite its sources?"

    parsed = ask(client, "Does it cite sources?", thread_id)

    [(system, user)] = fake_llm.rewrites
    assert "What does Turium build with Zebra?" in user
    assert "Answer from notes" in user
    assert user.rstrip().endswith("Does it cite sources?")
    assert done(parsed)["meta"]["search_query"] == "Does Zebra cite its sources?"
    # The answer is written for the standalone question too.
    assert fake_llm.calls[-1][1].endswith("Question: Does Zebra cite its sources?")


def test_rewrite_failure_falls_back_to_the_question(client, fake_llm):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    thread_id = ask(client, "What does Turium build with Zebra?")[0][1]["id"]
    fake_llm.fail_rewrite = True

    parsed = ask(client, "Does Zebra cite sources?", thread_id)

    assert done(parsed)["meta"]["search_query"] is None
    assert done(parsed)["answer"] == "Answer from notes [1]."


def test_saved_question_is_what_the_user_typed(client, fake_llm):
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    thread_id = ask(client, "What does Turium build with Zebra?")[0][1]["id"]
    fake_llm.rewritten = "Does Zebra cite its sources?"

    ask(client, "Does it cite sources?", thread_id)

    messages = client.get(f"/threads/{thread_id}").json()["messages"]
    assert messages[2]["content"] == "Does it cite sources?"
