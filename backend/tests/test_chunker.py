from app.services.chunker import chunk_text


def test_empty_returns_empty():
    assert chunk_text("   \n\n  ") == []


def test_short_text_single_chunk():
    assert chunk_text("Hello world.\n\nSecond paragraph.") == ["Hello world.\n\nSecond paragraph."]


def test_chunks_respect_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(40))

    chunks = chunk_text(text, size=1200, overlap=200)

    assert len(chunks) > 1
    assert all(len(c) <= 1200 for c in chunks)


def test_overlap_carries_context():
    text = "\n\n".join(f"Sentence number {i} talks about topic {i}." * 5 for i in range(30))

    chunks = chunk_text(text, size=500, overlap=100)

    for previous, current in zip(chunks, chunks[1:]):
        tail_words = previous.split()[-3:]
        assert " ".join(tail_words) in current


def test_oversized_paragraph_split():
    paragraph = " ".join(f"This is sentence {i} of a very long paragraph." for i in range(110))
    assert len(paragraph) > 5000

    chunks = chunk_text(paragraph, size=1200, overlap=200)

    assert len(chunks) >= 4


def test_sentence_longer_than_size_is_hard_split():
    chunks = chunk_text("x" * 3000, size=1200, overlap=200)

    assert len(chunks) >= 3
    assert all(len(c) <= 1200 for c in chunks)


def test_no_text_lost():
    words = [f"w{i}" for i in range(2000)]
    text = "\n\n".join(" ".join(words[i : i + 50]) + "." for i in range(0, 2000, 50))

    joined = " ".join(chunk_text(text, size=1200, overlap=200))

    assert all(word in joined.split() or word + "." in joined.split() for word in words)
