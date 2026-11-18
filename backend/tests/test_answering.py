from app.services.answering import build_prompt, parse_citations
from app.services.retrieval import Hit


def hit(n: int) -> Hit:
    return Hit(
        chunk_id=n,
        item_id=f"item{n}",
        title=f"Title {n}",
        source_type="note",
        url=None,
        text=f"Chunk text {n}",
        score=0.9,
    )


def test_parse_citations_ignores_out_of_range():
    assert parse_citations("a [1] b [7] c [1] [2]", 3) == [1, 2]


def test_parse_citations_handles_grouped_refs():
    assert parse_citations("Both say so [1, 3].", 3) == [1, 3]


def test_parse_citations_none():
    assert parse_citations("No refs here.", 3) == []


def test_system_prompt_asks_for_plain_text():
    system, _ = build_prompt("q?", [hit(1)])

    assert "no Markdown" in system


def test_build_prompt_numbers_sources():
    system, user = build_prompt("What is chunk 2?", [hit(1), hit(2)])

    assert "[1] Title 1 (note)\nChunk text 1" in user
    assert "[2] Title 2 (note)\nChunk text 2" in user
    assert user.endswith("Question: What is chunk 2?")
    assert "I couldn't find that in your saved items." in system


def test_sources_say_what_kind_of_item_they_are():
    # So "the link I shared" or "my PDF" can be matched to a source.
    page = Hit(3, "item3", "Proactive Agents", "url", "https://example.com/agents", "text", 0.9)

    _, user = build_prompt("What did the link I shared say?", [page])

    assert "[1] Proactive Agents (web page, https://example.com/agents)" in user


def test_system_prompt_handles_loose_questions_and_partial_answers():
    system, _ = build_prompt("q?", [hit(1)])

    assert "the link I shared" in system
    assert "only part of the question" in system
