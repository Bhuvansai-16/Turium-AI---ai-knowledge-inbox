from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.api import health, ingest, items, query, settings, threads
from app.config import get_settings
from app.errors import register_error_handlers
from app.log_setup import RequestContextMiddleware, configure_logging
from app.services import ingestion
from app.services.llm import get_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Honour dependency overrides so tests can resume work with a fake provider.
    ingestion.requeue_stuck_items(app.dependency_overrides.get(get_llm, get_llm))
    yield


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)

    app = FastAPI(title="AI Knowledge Inbox", version="1.0.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(items.router)
    app.include_router(query.router)
    app.include_router(settings.router)
    app.include_router(threads.router)
    return app


app = create_app()
