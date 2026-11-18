import copy
import hashlib
import re

import numpy as np

from app.services.llm import ProviderError

DIMENSIONS = 256


class FakeLLM:
    """Deterministic stand-in for the real provider.

    Embeddings are hashed bag-of-words vectors, so texts sharing words get high cosine
    similarity -- enough to exercise real retrieval logic without network calls.
    """

    embed_model = "fake-embed"
    chat_model = "fake-chat"

    def __init__(self, answer: str = "Answer from notes [1].", fail: bool = False, fail_mid_stream: bool = False):
        self.answer = answer
        self.fail = fail
        self.fail_mid_stream = fail_mid_stream
        self.calls: list[tuple[str, str]] = []
        # Follow-up rewriting: the standalone question to return (None = return the follow-up unchanged).
        self.rewritten: str | None = None
        self.fail_rewrite = False
        self.rewrites: list[tuple[str, str]] = []

    def embed(self, texts: list[str]) -> np.ndarray:
        if self.fail:
            raise ProviderError("fake provider is down")
        vectors = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS
                vectors[row, bucket] += 1
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def using(self, chat_model: str) -> "FakeLLM":
        clone = copy.copy(self)
        clone.chat_model = chat_model
        return clone

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def complete(self, system: str, user: str) -> str:
        if self.fail:
            raise ProviderError("fake provider is down")
        if system.startswith("Rewrite"):
            self.rewrites.append((system, user))
            if self.fail_rewrite:
                raise ProviderError("fake provider is down")
            return self.rewritten or user.rstrip().rsplit("\n", 1)[-1].removeprefix("Follow-up question: ")
        self.calls.append((system, user))
        return self.answer

    def stream_complete(self, system: str, user: str):
        """Yields the canned answer word by word, like a real token stream."""
        if self.fail:
            raise ProviderError("fake provider is down")
        self.calls.append((system, user))
        for i, word in enumerate(self.answer.split(" ")):
            if self.fail_mid_stream and i == 1:
                raise ProviderError("fake provider dropped the stream")
            yield word if i == 0 else " " + word


class FakeProvider:
    """Stands in for a provider during the Settings connection test.

    Model ids in `known` work; any other id fails the way a real provider rejects a typo.
    """

    def __init__(self, config, known: set[str], reachable: bool = True):
        self.embed_model = config.embed_model
        self.chat_model = config.chat_model
        self.known = known
        self.reachable = reachable

    def embed(self, texts: list[str]):
        if not self.reachable or self.embed_model not in self.known:
            raise ProviderError("Connection refused" if not self.reachable else "model not found")
        return np.zeros((len(texts), DIMENSIONS), dtype=np.float32)

    def using(self, chat_model: str) -> "FakeProvider":
        clone = copy.copy(self)
        clone.chat_model = chat_model
        return clone

    def complete(self, system: str, user: str) -> str:
        if self.chat_model not in self.known:
            raise ProviderError(f"The model `{self.chat_model}` does not exist")
        return "OK"
