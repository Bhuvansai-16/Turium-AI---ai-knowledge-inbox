import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.services.llm import get_llm
from tests.fakes import FakeLLM


@pytest.fixture
def settings_env(tmp_path, monkeypatch):
    """Point the app at a throwaway database and no real LLM key."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_API_KEY", "")
    # Pin provider settings so a developer's own backend/.env can't change test results.
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1/")
    monkeypatch.setenv("EMBED_QUERY_INSTRUCTION", "")
    monkeypatch.setenv("MIN_SCORE", "0.45")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(settings_env, fake_llm):
    """App wired to the fake LLM. Background tasks run before TestClient returns."""
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def unconfigured_client(settings_env):
    """App with no LLM key and no override: exercises the 503 path."""
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
