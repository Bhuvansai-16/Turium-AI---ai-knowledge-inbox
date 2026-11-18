import pytest

from app.config import get_settings
from app.services.answering import build_prompt, is_overview
from app.services.retrieval import Hit

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."
OFFSITE = "Team offsite: the 2027 engineering offsite is in Lisbon from 3 to 5 May."


@pytest.mark.parametrize(
    "question",
    [
        "What do my saved items have in common?",
        "Summarize everything I saved",
        "Give me an overview of my library",
        "What did I save recently?",
    ],
)
def test_overview_questions_are_recognised(question):
    assert is_overview(question)


@pytest.mark.parametrize("question", ["When is the Acme renewal?", "Summary of the Zebra launch plan"])
def test_specific_questions_are_not_overview(question):
    assert not is_overview(question)


def test_overview_answers_from_every_item(client, fake_llm, settings_env):
    # A strict floor: normal retrieval would find nothing for this question.
    settings_env.setenv("MIN_SCORE", "0.99")
    get_settings.cache_clear()
    client.post("/ingest", json={"type": "note", "content": ZEBRA})
    client.post("/ingest", json={"type": "note", "content": OFFSITE})
    fake_llm.answer = "Both are about plans at Turium [1] [2]."

    body = client.post("/query", json={"question": "What do my saved items have in common?"}).json()

    prompt = fake_llm.calls[-1][1]
    assert "Turium builds Zebra" in prompt
    assert "Team offsite" in prompt
    assert len(body["sources"]) == 2


def test_overview_prompt_allows_saying_items_differ():
    # The strict "reply exactly: not found" rule made real models refuse unrelated libraries.
    hit = Hit(1, "a", "Note", "note", None, "text", 0.2)
    assert "nothing in common" in build_prompt("What do my saved items have in common?", [hit])[0]
    assert "nothing in common" not in build_prompt("When is the Acme renewal?", [hit])[0]
