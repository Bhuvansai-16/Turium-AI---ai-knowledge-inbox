"""The only place that talks to model providers, through LangChain's integrations.

LangChain is used for what it is good at here: one interface over many providers (any
OpenAI-compatible API, plus native Gemini). Chunking, retrieval, prompting and citation
parsing stay in this codebase on purpose; they are the parts worth reading and testing.

The rest of the app only sees LLMClient's four methods, and tests swap in a deterministic
fake through FastAPI's dependency overrides.
"""

import time
from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Any

import numpy as np
import structlog
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app import provider_config
from app.errors import AppError
from app.provider_config import ProviderConfig

EMBED_BATCH_SIZE = 64
TIMEOUT_SECONDS = 30
MAX_RETRIES = 2

log = structlog.get_logger()


class ProviderError(Exception):
    """The model provider failed after the integration's own retries."""


class LLMClient:
    def __init__(
        self,
        chat: BaseChatModel,
        embeddings: Embeddings,
        chat_model: str,
        embed_model: str,
        query_instruction: str = "",
        chat_factory: Callable[[str], BaseChatModel] | None = None,
    ):
        self.chat = chat
        self.embeddings = embeddings
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.query_instruction = query_instruction
        self._chat_factory = chat_factory

    def using(self, chat_model: str) -> "LLMClient":
        """Same provider and embeddings, different chat model (the question box's model picker)."""
        if self._chat_factory is None:
            raise ValueError("This client can't switch chat models")
        return LLMClient(
            self._chat_factory(chat_model),
            self.embeddings,
            chat_model,
            self.embed_model,
            self.query_instruction,
            self._chat_factory,
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        """L2-normalized float32 vectors, one row per text, so dot product == cosine similarity."""
        rows = self._call("embed", self.embed_model, lambda: self.embeddings.embed_documents(texts))
        vectors = np.asarray(rows, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a search query. Instruction-tuned embedders (Qwen3-Embedding, E5-instruct) score
        better when queries carry a task description and documents do not."""
        if self.query_instruction:
            text = f"Instruct: {self.query_instruction}\nQuery: {text}"
        return self.embed([text])[0]

    def complete(self, system: str, user: str) -> str:
        message = self._call("complete", self.chat_model, lambda: self.chat.invoke(_messages(system, user)))
        return message.text.strip()

    def stream_complete(self, system: str, user: str) -> Iterator[str]:
        """Yields answer text as the model produces it. Errors can arrive mid-stream, so the
        whole iteration is wrapped, not just the initial request."""
        started = time.perf_counter()
        try:
            for chunk in self.chat.stream(_messages(system, user)):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            log.warning("llm.error", operation="stream", model=self.chat_model, error=type(exc).__name__)
            raise ProviderError(str(exc)) from exc
        log.info("llm.call", operation="stream", model=self.chat_model, duration_ms=_ms(started))

    def _call(self, operation: str, model: str, fn: Callable[[], Any]) -> Any:
        # Every provider's SDK raises its own exception types; at this boundary they all mean
        # "the provider failed", so they become one ProviderError the API maps to 502.
        started = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            log.warning("llm.error", operation=operation, model=model, error=type(exc).__name__)
            raise ProviderError(str(exc)) from exc
        log.info("llm.call", operation=operation, model=model, duration_ms=_ms(started))
        return result


def _messages(system: str, user: str) -> list:
    return [SystemMessage(content=system), HumanMessage(content=user)]


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def client_for(config: ProviderConfig) -> LLMClient:
    return _build_client(
        config.provider,
        config.base_url,
        config.api_key,
        config.chat_model,
        config.embed_model,
        config.query_instruction,
    )


@lru_cache
def _build_client(
    provider: str,
    base_url: str,
    api_key: str | None,
    chat_model: str,
    embed_model: str,
    query_instruction: str,
) -> LLMClient:
    if provider == "gemini":

        def make_chat(model: str) -> BaseChatModel:
            return ChatGoogleGenerativeAI(model=model, api_key=api_key, retries=MAX_RETRIES)

        embeddings = GoogleGenerativeAIEmbeddings(model=embed_model, api_key=api_key)
    else:
        # OpenAI and any OpenAI-compatible endpoint (Ollama, Nebius, Groq...). Local servers
        # ignore the key, but the SDK requires a non-empty one.
        key = api_key or "not-needed"

        def make_chat(model: str) -> BaseChatModel:
            # No temperature: reasoning models (OpenAI's o-series, GPT-5 and later) reject any
            # value but the default. Grounding comes from the prompt and citations instead.
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=key,
                max_retries=MAX_RETRIES,
                timeout=TIMEOUT_SECONDS,
            )

        embeddings = OpenAIEmbeddings(
            model=embed_model,
            base_url=base_url,
            api_key=key,
            check_embedding_ctx_length=False,  # it would tokenize with OpenAI's tokenizer
            chunk_size=EMBED_BATCH_SIZE,
            max_retries=MAX_RETRIES,
            timeout=TIMEOUT_SECONDS,
        )
    return LLMClient(make_chat(chat_model), embeddings, chat_model, embed_model, query_instruction, make_chat)


def get_llm() -> LLMClient:
    """FastAPI dependency. Fails with a clear 503 instead of a crash when no provider is set up."""
    config = provider_config.load()
    if not config.configured:
        raise AppError(
            503,
            "provider_not_configured",
            "No AI provider connected. Open Settings to add an API key or connect an OpenAI-compatible server.",
        )
    return client_for(config)
