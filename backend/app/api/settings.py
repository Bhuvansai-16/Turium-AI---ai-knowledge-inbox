from dataclasses import replace
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, StringConstraints

from app import db, provider_config, repository
from app.errors import AppError
from app.provider_config import PRESETS, ProviderConfig
from app.services import ingestion
from app.services.llm import ProviderError, client_for, get_llm

router = APIRouter()

ProviderName = Literal["openai", "gemini", "custom"]
ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ApiKey = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)]


class ProviderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    base_url: AnyHttpUrl
    api_key: ApiKey = None


class SettingsIn(ProviderIn):
    chat_model: ModelName
    embed_model: ModelName
    # Extra chat models to offer in the question box's model picker.
    chat_models: list[ModelName] = []


class SettingsOut(BaseModel):
    provider: str
    base_url: str
    chat_model: str
    chat_models: list[str]
    embed_model: str
    api_key_set: bool
    api_key_hint: str | None
    # Masked hint of the key saved for each provider, e.g. {"openai": "••••9876"}.
    key_hints: dict[str, str]
    presets: dict

    @classmethod
    def from_config(cls, config: ProviderConfig) -> "SettingsOut":
        return cls(
            provider=config.provider,
            base_url=config.base_url,
            chat_model=config.chat_model,
            chat_models=config.enabled_chat_models,
            embed_model=config.embed_model,
            api_key_set=bool(config.api_key),
            api_key_hint=config.api_key_hint,
            key_hints={name: f"••••{key[-4:]}" for name, key in provider_config.saved_keys().items()},
            presets=PRESETS,
        )


@router.get("/settings", response_model=SettingsOut)
def get_settings_route() -> SettingsOut:
    """Current provider. The API key itself is never returned, only whether one is set."""
    return SettingsOut.from_config(provider_config.load())


@router.put("/settings")
def save_settings(request: SettingsIn, http: Request, background: BackgroundTasks) -> dict:
    """Test the connection, save, and re-index the library if the embedding model changed."""
    previous = provider_config.load()
    config = replace(
        _candidate(request, request.chat_model, request.embed_model),
        chat_models=tuple(request.chat_models),
    )

    _test_connection(config)
    provider_config.save(config)

    reindexing = 0
    if config.embed_model != previous.embed_model:
        # Old vectors live in a different embedding space, so every item is re-embedded.
        with db.connect() as conn:
            item_ids = repository.all_item_ids(conn)
            for item_id in item_ids:
                repository.reset_for_retry(conn, item_id)
        llm = http.app.dependency_overrides.get(get_llm, get_llm)()
        for item_id in item_ids:
            background.add_task(ingestion.run_ingestion, item_id, llm)
        reindexing = len(item_ids)

    return {"settings": SettingsOut.from_config(config), "reindexing": reindexing}


def _candidate(request: ProviderIn, chat_model: str, embed_model: str) -> ProviderConfig:
    """Build the config to test. An omitted key reuses the one saved for that provider."""
    previous = provider_config.load()
    preset = PRESETS[request.provider]
    api_key = request.api_key or provider_config.saved_keys().get(request.provider)
    if preset["needs_key"] and not api_key:
        raise AppError(422, "api_key_required", f"{preset['label']} needs an API key")

    # Same provider: keep tuned values (e.g. MIN_SCORE from .env). New provider: its defaults.
    same = previous.provider == request.provider
    return ProviderConfig(
        provider=request.provider,
        base_url=str(request.base_url),
        api_key=api_key,
        chat_model=chat_model,
        embed_model=embed_model,
        query_instruction=previous.query_instruction if same else preset["query_instruction"],
        min_score=previous.min_score if same else preset["min_score"],
    )


def _test_connection(config: ProviderConfig) -> None:
    """Make the calls the app will make, so a wrong URL, key or model id fails here, not later.

    One embedding call checks the URL, the key and the embedding model together. Then each
    enabled chat model answers a one-word prompt. Model ids are typed by the user rather than
    picked from a list, because not every provider can list its models (Gemini can't here).
    """
    client = client_for(config)
    try:
        client.embed(["connection test"])
    except ProviderError as exc:
        raise AppError(
            400,
            "provider_unreachable",
            "Could not connect with these settings. Check the URL, the API key and the embedding model ID"
            + (", and that the server is running." if config.provider == "custom" else "."),
            {"reason": str(exc)[:300]},
        )
    for model in config.enabled_chat_models:
        try:
            client.using(model).complete("Reply with the single word OK.", "OK")
        except ProviderError as exc:
            raise AppError(
                422,
                "model_not_found",
                f"Connected, but the chat model '{model}' didn't respond. Check its ID.",
                {"model": model, "reason": str(exc)[:300]},
            )
