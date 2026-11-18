"""Hybrid retrieval: vector similarity and keyword (BM25) search, merged by rank.

Vectors catch meaning ("when does the contract end" finds "renewal is due"); keywords catch
exact terms embeddings blur (invoice numbers, names, error codes). Each produces a ranked list
and Reciprocal Rank Fusion merges them, so neither score scale needs calibrating against the
other. The relevance floor applies to the vector side only: an exact keyword hit is relevant
by definition, even when its embedding similarity is low.

Vectors are L2-normalized on write, so one matrix-vector product gives every cosine score.
That is O(n) per query and loads all vectors into memory: fine up to roughly 100k chunks on a
laptop. Past that, swap for an ANN index (pgvector HNSW, Qdrant, FAISS).
"""

import re
from itertools import combinations
import sqlite3
from dataclasses import dataclass

import numpy as np

from app import repository

CANDIDATES = 50  # how deep each list goes before fusion
MAX_TERMS = 8  # keyword terms used per question (8 terms = 28 pairs)
RRF_K = 60  # standard constant from the RRF paper; damps the advantage of rank 1 vs rank 2

STOPWORDS = frozenset(
    "a an and are as at be but by can could did do does for from had has have how i if in is it its "
    "me my of on or our so that the their them there these they this to was we were what when where "
    "which who whom why will with would you your about tell show give find any all".split()
)


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    item_id: str
    title: str
    source_type: str
    url: str | None
    text: str
    score: float


def keyword_query(text: str) -> str | None:
    """An FTS5 query matching passages that share at least two meaningful words with the question
    (or its only one). Terms are quoted, so no FTS syntax can leak in from user input.

    Keyword hits skip the relevance floor, so they must be precise: with a plain OR, one shared
    word ("policy") would make any passage containing it "relevant". Requiring every word would
    miss "Status of INV-20931?" because the passage never says "status". Two words is the middle.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    terms = list(dict.fromkeys(t for t in words if len(t) >= 2 and t not in STOPWORDS))[:MAX_TERMS]
    if len(terms) <= 1:
        return f'"{terms[0]}"' if terms else None
    return " OR ".join(f'("{a}" AND "{b}")' for a, b in combinations(terms, 2))


def search(
    conn: sqlite3.Connection, question: str, query_vec: np.ndarray, k: int, min_score: float, model: str
) -> list[Hit]:
    chunk_ids, matrix = repository.load_vectors(conn, model)
    if not chunk_ids:
        return []
    scores = matrix @ query_vec
    position = {chunk_id: i for i, chunk_id in enumerate(chunk_ids)}

    top = np.argsort(-scores)[:CANDIDATES]
    vector_ranked = [chunk_ids[i] for i in top if scores[i] >= min_score]
    fts_query = keyword_query(question)
    keyword_ranked = repository.keyword_search(conn, fts_query, model, CANDIDATES) if fts_query else []
    # A chunk committed by background ingestion between the two reads has no vector score yet.
    keyword_ranked = [chunk_id for chunk_id in keyword_ranked if chunk_id in position]

    fused: dict[int, float] = {}
    for ranked in (vector_ranked, keyword_ranked):
        for rank, chunk_id in enumerate(ranked):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1 / (RRF_K + rank + 1)
    best = sorted(fused, key=fused.__getitem__, reverse=True)[:k]

    return _hits(conn, best, {chunk_id: float(scores[position[chunk_id]]) for chunk_id in best})


def overview(conn: sqlite3.Connection, query_vec: np.ndarray, model: str, limit: int) -> list[Hit]:
    """The opening passage of each item, for questions about the library as a whole."""
    chunk_ids, matrix = repository.load_vectors(conn, model)
    if not chunk_ids:
        return []
    position = {chunk_id: i for i, chunk_id in enumerate(chunk_ids)}
    opening = [cid for cid in repository.opening_chunk_ids(conn, model, limit) if cid in position]
    return _hits(conn, opening, {cid: float(matrix[position[cid]] @ query_vec) for cid in opening})


def _hits(conn: sqlite3.Connection, ordered_ids: list[int], scores: dict[int, float]) -> list[Hit]:
    rows = {row["id"]: row for row in repository.get_chunks(conn, ordered_ids)}
    return [
        Hit(
            chunk_id=chunk_id,
            item_id=rows[chunk_id]["item_id"],
            title=rows[chunk_id]["title"],
            source_type=rows[chunk_id]["source_type"],
            url=rows[chunk_id]["url"],
            text=rows[chunk_id]["text"],
            score=scores[chunk_id],
        )
        for chunk_id in ordered_ids
        if chunk_id in rows
    ]
