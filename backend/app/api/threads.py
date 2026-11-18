from fastapi import APIRouter, Response

from app import db, repository
from app.services.conversations import thread_not_found

router = APIRouter()


def _thread_out(row) -> dict:
    return {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


@router.get("/threads")
def list_threads() -> dict:
    """Conversation history, most recently used first."""
    with db.connect() as conn:
        return {"threads": [_thread_out(row) for row in repository.list_threads(conn)]}


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str) -> dict:
    """One conversation with every question and answer, including the cited sources."""
    with db.connect() as conn:
        row = repository.get_thread(conn, thread_id)
        if row is None:
            raise thread_not_found(thread_id)
        return {**_thread_out(row), "messages": repository.thread_messages(conn, thread_id)}


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str) -> Response:
    with db.connect() as conn:
        if not repository.delete_thread(conn, thread_id):
            raise thread_not_found(thread_id)
    return Response(status_code=204)
