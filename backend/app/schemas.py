import sqlite3
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

MAX_NOTE_CHARS = 20_000
PREVIEW_CHARS = 200

NoteContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NOTE_CHARS)]
OptionalTitle = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=200)]
ItemStatus = Literal["pending", "processing", "ready", "failed"]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["note"]
    content: NoteContent
    title: OptionalTitle = None


class UrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["url"]
    url: Annotated[HttpUrl, Field(max_length=2048)]


IngestRequest = Annotated[NoteIn | UrlIn, Field(discriminator="type")]


class ItemOut(BaseModel):
    id: str
    title: str
    source_type: Literal["note", "url", "file"]
    url: str | None
    status: ItemStatus
    error: str | None
    preview: str
    chunk_count: int
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "ItemOut":
        return cls(
            id=row["id"],
            title=row["title"],
            source_type=row["source_type"],
            url=row["url"],
            status=row["status"],
            error=row["error"],
            preview=" ".join(row["raw_content"].split())[:PREVIEW_CHARS],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
        )


class ItemList(BaseModel):
    items: list[ItemOut]


class QueryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]
    top_k: Annotated[int, Field(ge=1, le=10)] = 5
    # Chat model for this question; must be one enabled in Settings. Omit for the default.
    model: Annotated[str | None, StringConstraints(max_length=200)] = None


class StreamQueryIn(QueryIn):
    """POST /query/stream also saves the conversation; omit thread_id to start a new thread."""

    thread_id: Annotated[str | None, StringConstraints(max_length=64)] = None


class SourceOut(BaseModel):
    ref: int
    item_id: str
    title: str
    source_type: Literal["note", "url", "file"]
    url: str | None
    snippet: str
    score: float


class QueryMeta(BaseModel):
    model: str
    retrieved: int
    latency_ms: int
    # Set when a follow-up was rewritten into a standalone question before searching.
    search_query: str | None = None


class QueryOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    meta: QueryMeta
