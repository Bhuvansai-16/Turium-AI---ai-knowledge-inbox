from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables and backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1/"
    embed_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-6-luna"
    # Task description prepended to search queries (not documents), for instruction-tuned
    # embedding models such as Qwen3-Embedding. Empty for OpenAI and Gemini.
    embed_query_instruction: str = ""

    db_path: str = "data/inbox.db"
    min_score: float = 0.3
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
