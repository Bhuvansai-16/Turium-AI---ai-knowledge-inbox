"""Paragraph-aware chunking.

Paragraphs are the natural semantic unit of notes and articles, so we pack whole paragraphs
into chunks of up to `size` characters and only fall back to sentence (then hard character)
splits when a single paragraph is too large. Each chunk starts with the tail of the previous
one (`overlap` chars) so a fact straddling a boundary is still retrievable.

Sizes are in characters, not tokens: the embedding model's tokenizer differs per provider and
~4 chars/token is accurate enough at this scale (1200 chars ~ 300 tokens).
"""

import re

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    pieces = _split_into_pieces(text, size)
    chunks: list[str] = []
    current = ""

    for piece in pieces:
        if current and len(current) + 2 + len(piece) > size:
            chunks.append(current)
            room = size - len(piece) - 2  # overlap counts toward the size limit
            current = _tail(current, min(overlap, room)) if room > 0 else ""
        current = f"{current}\n\n{piece}" if current else piece

    if current:
        chunks.append(current)
    return chunks


def _split_into_pieces(text: str, size: int) -> list[str]:
    """Normalized paragraphs, each guaranteed to be at most `size` characters."""
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        if len(paragraph) <= size:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long_paragraph(paragraph, size))
    return pieces


def _split_long_paragraph(paragraph: str, size: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for sentence in SENTENCE_END.split(paragraph):
        if len(sentence) > size:
            if current:
                parts.append(current)
                current = ""
            parts.extend(sentence[i : i + size] for i in range(0, len(sentence), size))
        elif current and len(current) + 1 + len(sentence) > size:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current:
        parts.append(current)
    return parts


def _tail(text: str, length: int) -> str:
    """Last `length` chars, moved forward to a word boundary so we don't start mid-word."""
    tail = text[-length:]
    if len(text) > length and not text[-length - 1].isspace() and " " in tail:
        tail = tail.split(" ", 1)[1]
    return tail.strip()
