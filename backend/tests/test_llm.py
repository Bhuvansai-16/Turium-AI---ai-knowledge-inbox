from types import SimpleNamespace

import numpy as np
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.errors import AppError
from app.provider_config import ProviderConfig
from app.services.llm import LLMClient, ProviderError, client_for, get_llm


class FakeEmbeddings:
    def __init__(self, fail=False):
        self.seen: list[str] = []
        self.fail = fail

    def embed_documents(self, texts):
        if self.fail:
            raise RuntimeError("connection refused")
        self.seen.extend(texts)
        return [[3.0, 4.0] for _ in texts]


class FakeChat:
    def __init__(self, chunks=("Ans", "", "wer [1]."), fail_after=None):
        self.chunks = chunks
        self.fail_after = fail_after

    def invoke(self, messages):
        return SimpleNamespace(text="Answer [1].")

    def stream(self, messages):
        for i, text in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("stream dropped")
            yield SimpleNamespace(text=text)


def make_client(chat=None, embeddings=None, query_instruction="") -> LLMClient:
    return LLMClient(
        chat=chat or FakeChat(),
        embeddings=embeddings or FakeEmbeddings(),
        chat_model="chat",
        embed_model="embed",
        query_instruction=query_instruction,
    )


def config(provider: str, **overrides) -> ProviderConfig:
    values = dict(
        provider=provider,
        base_url="https://llm.test/v1/",
        api_key="key-123",
        chat_model="chat-a",
        embed_model="embed-a",
        query_instruction="",
        min_score=0.4,
    )
    return ProviderConfig(**{**values, **overrides})


def test_embed_normalizes_rows():
    vectors = make_client().embed(["a", "b", "c"])

    assert vectors.shape == (3, 2)
    assert vectors.dtype == np.float32
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_embed_query_prefixes_instruction():
    embeddings = FakeEmbeddings()
    client = make_client(embeddings=embeddings, query_instruction="find answers")

    vector = client.embed_query("when is renewal?")

    assert embeddings.seen == ["Instruct: find answers\nQuery: when is renewal?"]
    assert vector.shape == (2,)


def test_embed_query_without_instruction_is_plain():
    embeddings = FakeEmbeddings()

    make_client(embeddings=embeddings).embed_query("hello")

    assert embeddings.seen == ["hello"]


def test_complete_returns_text():
    assert make_client().complete("system", "user") == "Answer [1]."


def test_stream_complete_skips_empty_chunks():
    assert list(make_client().stream_complete("system", "user")) == ["Ans", "wer [1]."]


def test_stream_error_mid_way_becomes_provider_error():
    stream = make_client(chat=FakeChat(chunks=("Partial", "more"), fail_after=1)).stream_complete("s", "u")

    assert next(stream) == "Partial"
    with pytest.raises(ProviderError):
        next(stream)


def test_provider_failure_becomes_provider_error():
    with pytest.raises(ProviderError):
        make_client(embeddings=FakeEmbeddings(fail=True)).embed(["hello"])


def test_openai_compatible_providers_use_langchain_openai():
    client = client_for(config("openai"))

    assert isinstance(client.chat, ChatOpenAI)
    assert isinstance(client.embeddings, OpenAIEmbeddings)
    assert client.chat.openai_api_base == "https://llm.test/v1/"
    assert client.embeddings.check_embedding_ctx_length is False  # non-OpenAI tokenizers
    assert client.embeddings.chunk_size == 64


def test_local_provider_without_key_still_builds():
    client = client_for(config("custom", api_key=None))

    assert isinstance(client.chat, ChatOpenAI)


def test_gemini_uses_native_langchain_integration():
    client = client_for(config("gemini", chat_model="gemini-3.5-flash-lite", embed_model="gemini-embedding-001"))

    assert isinstance(client.chat, ChatGoogleGenerativeAI)
    assert isinstance(client.embeddings, GoogleGenerativeAIEmbeddings)


def test_get_llm_without_key_503(settings_env):
    with pytest.raises(AppError) as err:
        get_llm()

    assert err.value.status == 503
    assert err.value.code == "provider_not_configured"


def test_chat_sends_no_temperature():
    # Reasoning models (o-series, GPT-5 and later) reject any temperature but the default.
    from app.services.llm import _build_client

    client = _build_client("openai", "https://api.openai.com/v1/", "sk-test", "gpt-x", "embed-x", "")
    assert client.chat.temperature is None
    assert "temperature" not in client.chat._default_params or client.chat._default_params["temperature"] is None
