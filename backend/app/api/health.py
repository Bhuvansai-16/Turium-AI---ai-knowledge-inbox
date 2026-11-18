from fastapi import APIRouter

from app import db, provider_config

router = APIRouter()


@router.get("/health")
def health() -> dict:
    with db.connect() as conn:
        conn.execute("SELECT 1")
    config = provider_config.load()
    return {
        "status": "ok",
        "db": "ok",
        "llm_configured": config.configured,
        "provider": config.provider,
        "chat_model": config.chat_model,
        "embed_model": config.embed_model,
    }
