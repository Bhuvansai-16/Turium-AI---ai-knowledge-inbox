import json
from itertools import chain

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import db, provider_config, repository
from app.errors import AppError
from app.schemas import QueryIn, QueryOut, StreamQueryIn
from app.services import answering, conversations
from app.services.llm import LLMClient, ProviderError, get_llm

router = APIRouter()


def _upstream_error() -> AppError:
    return AppError(502, "upstream_error", "The AI provider failed to respond. Try again.")


def _with_model(llm: LLMClient, model: str | None) -> LLMClient:
    """Switch to the model picked in the question box, if it is one enabled in Settings."""
    if model is None or model == llm.chat_model:
        return llm
    enabled = provider_config.load().enabled_chat_models
    if model not in enabled:
        raise AppError(
            422,
            "model_not_enabled",
            f"'{model}' isn't enabled. Add it in Settings first.",
            {"model": model, "enabled": enabled},
        )
    return llm.using(model)


@router.post("/query", response_model=QueryOut)
def query(request: QueryIn, llm: LLMClient = Depends(get_llm)) -> QueryOut:
    """Answer a question from saved items, with numbered citations to the chunks used."""
    llm = _with_model(llm, request.model)
    try:
        return answering.answer_question(llm, request.question, request.top_k, provider_config.load().min_score)
    except ProviderError:
        raise _upstream_error()


@router.post("/query/stream", response_class=StreamingResponse)
def query_stream(request: StreamQueryIn, llm: LLMClient = Depends(get_llm)) -> StreamingResponse:
    """Same as POST /query, streamed as Server-Sent Events: `thread` (which conversation this
    was saved to), `sources`, then `token`s, then `done` (the full /query payload) or `error`.

    Retrieval runs before the stream opens, so validation, configuration and embedding
    failures still come back as normal HTTP errors rather than mid-stream events.
    """
    llm = _with_model(llm, request.model)
    if request.thread_id is not None:
        with db.connect() as conn:
            if repository.get_thread(conn, request.thread_id) is None:
                raise conversations.thread_not_found(request.thread_id)

    # A follow-up in an existing chat is rewritten into a standalone question first.
    history = conversations.history(request.thread_id) if request.thread_id else []
    question = answering.standalone_question(llm, history, request.question)

    try:
        retrieval = answering.retrieve(
            llm, question, request.top_k, provider_config.load().min_score, rewritten=question != request.question
        )
    except ProviderError:
        raise _upstream_error()

    thread_id, title = conversations.start_turn(request.thread_id, request.question)
    events = chain(
        [("thread", {"id": thread_id, "title": title})],
        conversations.record_answer(thread_id, answering.stream_answer(llm, question, retrieval)),
    )
    return StreamingResponse(
        (f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
