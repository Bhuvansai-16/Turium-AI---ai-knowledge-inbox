"""Which LLM provider the app talks to.

Starts from backend/.env, and can be changed at runtime from the UI's settings dialog. Runtime
changes are saved to provider.json next to the database (already gitignored with the data dir).

The API key is stored in that local file so the choice survives a restart; it is never sent
back to the browser. In a multi-user deployment this would sit behind admin auth and the key
would live in a secrets manager.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings

# Defaults per provider. min_score is embedding-model specific: the cosine similarity below
# which a passage counts as unrelated (see README for how it was tuned).
PRESETS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1/",
        "chat_model": "gpt-6-luna",
        "embed_model": "text-embedding-3-small",
        "query_instruction": "",
        "min_score": 0.3,
        "needs_key": True,
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/",
        "chat_model": "gemini-3.5-flash-lite",
        "embed_model": "gemini-embedding-001",
        "query_instruction": "",
        "min_score": 0.45,
        "needs_key": True,
    },
    "custom": {
        # Ollama, Nebius, Groq, OpenRouter, vLLM... anything that speaks the OpenAI API.
        "label": "OpenAI-compatible",
        "base_url": "",
        "chat_model": "",
        "embed_model": "",
        "query_instruction": "",
        "min_score": 0.35,
        "needs_key": False,
    },
}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key: str | None
    chat_model: str
    embed_model: str
    query_instruction: str
    min_score: float
    # Extra chat models offered in the question box's model picker (the default is always included).
    chat_models: tuple[str, ...] = ()

    @property
    def enabled_chat_models(self) -> list[str]:
        return list(dict.fromkeys([self.chat_model, *self.chat_models]))

    @property
    def needs_key(self) -> bool:
        return PRESETS.get(self.provider, PRESETS["custom"])["needs_key"]

    @property
    def configured(self) -> bool:
        return bool(self.api_key) or not self.needs_key

    @property
    def api_key_hint(self) -> str | None:
        return f"••••{self.api_key[-4:]}" if self.api_key else None


def _path() -> Path:
    return Path(get_settings().db_path).parent / "provider.json"


def _read() -> dict | None:
    path = _path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load() -> ProviderConfig:
    data = _read()
    if data is None:
        return _from_env()
    data.pop("keys", None)
    return ProviderConfig(**{**data, "chat_models": tuple(data.get("chat_models", ()))})


def saved_keys() -> dict[str, str]:
    """API keys saved per provider, so switching back to one doesn't ask for its key again."""
    keys = dict((_read() or {}).get("keys", {}))
    current = load()
    if current.api_key:
        keys.setdefault(current.provider, current.api_key)
    return keys


def save(config: ProviderConfig) -> None:
    keys = saved_keys()
    if config.api_key:
        keys[config.provider] = config.api_key
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**asdict(config), "keys": keys}, indent=2), encoding="utf-8")


def _from_env() -> ProviderConfig:
    settings = get_settings()
    provider = next(
        (name for name, preset in PRESETS.items() if preset["base_url"] == settings.llm_base_url),
        "custom",
    )
    return ProviderConfig(
        provider=provider,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or None,
        chat_model=settings.chat_model,
        embed_model=settings.embed_model,
        query_instruction=settings.embed_query_instruction,
        min_score=settings.min_score,
    )
