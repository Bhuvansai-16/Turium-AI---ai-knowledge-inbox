"""Chat history: questions and answers saved per thread, so the sidebar can list past chats.

The last few turns are also used to rewrite a follow-up into a standalone question before
retrieval. The answer itself is still grounded only in retrieved sources, never in old answers.
"""

from collections.abc import Iterator

from app import db, repository
from app.errors import AppError
from app.services.ingestion import note_title


def thread_not_found(thread_id: str) -> AppError:
    return AppError(404, "thread_not_found", "No conversation with this id", {"thread_id": thread_id})


def history(thread_id: str, turns: int = 3) -> list[tuple[str, str]]:
    """The last few (question, answer) pairs of a thread, oldest first, for follow-up rewriting.

    Each question is paired with the answer right after it. A question can be saved without an
    answer (the server restarted mid-stream), so pairing by position would shift every later pair.
    """
    with db.connect() as conn:
        messages = repository.thread_messages(conn, thread_id)
    pairs = [
        (question["content"], answer["content"])
        for question, answer in zip(messages, messages[1:])
        if question["role"] == "user" and answer["role"] == "assistant" and answer["content"]
    ]
    return pairs[-turns:]


def start_turn(thread_id: str | None, question: str) -> tuple[str, str]:
    """Save the question, creating the thread on the first one. Returns (thread_id, title)."""
    with db.connect() as conn:
        if thread_id is None:
            title = note_title(question)
            thread_id = repository.create_thread(conn, title)
        else:
            thread = repository.get_thread(conn, thread_id)
            if thread is None:  # deleted while the question was being retrieved
                raise thread_not_found(thread_id)
            title = thread["title"]
        repository.add_message(conn, thread_id, "user", question)
    return thread_id, title


def record_answer(thread_id: str, events: Iterator[tuple[str, dict]]) -> Iterator[tuple[str, dict]]:
    """Pass stream events through unchanged and save the assistant's answer when the stream ends.

    The save runs in `finally`, so it also happens when the client disconnects mid-answer
    (the generator is closed): whatever text arrived is kept with status "stopped".
    """
    parts: list[str] = []
    final: dict | None = None
    status = "stopped"
    try:
        for name, data in events:
            if name == "token":
                parts.append(data["text"])
            elif name == "done":
                final, status = data, "done"
            elif name == "error":
                status = "error"
            yield name, data
    finally:
        with db.connect() as conn:
            repository.add_message(
                conn,
                thread_id,
                "assistant",
                final["answer"] if final else "".join(parts).strip(),
                status=status,
                sources=final["sources"] if final else [],
                meta=final["meta"] if final else None,
            )
