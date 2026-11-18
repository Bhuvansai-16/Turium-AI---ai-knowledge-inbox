import pytest
from fastapi.testclient import TestClient

from app.api import settings as settings_api
from app.services import ingestion
from app.services.fetcher import FetchedPage
from tests.fakes import FakeProvider

OPENAI = {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1/",
    "api_key": "sk-secret-key-9876",
    "chat_model": "chat-a",
    "embed_model": "embed-a",
}
LOCAL = {  # e.g. Ollama, through the OpenAI-compatible option
    "provider": "custom",
    "base_url": "http://localhost:11434/v1/",
    "chat_model": "llama3.1",
    "embed_model": "nomic-embed-text",
}


@pytest.fixture
def provider_models(monkeypatch):
    """Pretend every provider is reachable and serves these models."""
    known = {"chat-a", "embed-a", "llama3.1", "nomic-embed-text"}
    monkeypatch.setattr(settings_api, "client_for", lambda config: FakeProvider(config, known))
    return known


def test_defaults_come_from_env(client):
    body = client.get("/settings").json()

    assert body["provider"] == "openai"
    assert body["api_key_set"] is False
    assert "api_key" not in body
    assert set(body["presets"]) == {"openai", "gemini", "custom"}


def test_saving_key_never_echoes_it(client, provider_models):
    response = client.put("/settings", json=OPENAI)

    assert response.status_code == 200
    saved = response.json()["settings"]
    assert saved["api_key_set"] is True
    assert saved["api_key_hint"] == "••••9876"
    assert "sk-secret-key-9876" not in response.text
    assert "sk-secret-key-9876" not in client.get("/settings").text


def test_saved_provider_drives_health(client, provider_models):
    client.put("/settings", json=OPENAI)

    health = client.get("/health").json()

    assert health["llm_configured"] is True
    assert health["chat_model"] == "chat-a"
    assert health["provider"] == "openai"


def test_compatible_server_needs_no_key(client, provider_models):
    response = client.put("/settings", json=LOCAL)

    assert response.status_code == 200
    assert client.get("/health").json()["llm_configured"] is True


def test_cloud_provider_requires_key(client, provider_models):
    response = client.put("/settings", json={**OPENAI, "api_key": None})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "api_key_required"


def test_saved_key_kept_when_omitted(client, provider_models):
    client.put("/settings", json=OPENAI)

    response = client.put("/settings", json={**OPENAI, "api_key": None, "chat_model": "chat-a"})

    assert response.status_code == 200
    assert response.json()["settings"]["api_key_hint"] == "••••9876"


def test_unreachable_provider_is_rejected_and_not_saved(client, monkeypatch):
    monkeypatch.setattr(settings_api, "client_for", lambda config: FakeProvider(config, set(), reachable=False))

    response = client.put("/settings", json=LOCAL)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_unreachable"
    assert client.get("/settings").json()["provider"] == "openai"


def test_mistyped_chat_model_is_named_and_not_saved(client, provider_models):
    response = client.put("/settings", json={**OPENAI, "chat_model": "does-not-exist"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "model_not_found"
    assert error["details"]["model"] == "does-not-exist"
    assert "does not exist" in error["details"]["reason"]
    assert client.get("/settings").json()["provider"] == "openai"
    assert client.get("/settings").json()["api_key_set"] is False


def test_mistyped_embedding_model_fails_the_connection_test(client, provider_models):
    response = client.put("/settings", json={**OPENAI, "embed_model": "embed-typo"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_unreachable"
    assert "embedding model" in response.json()["error"]["message"]


def test_gemini_is_tested_like_any_provider(client, monkeypatch):
    known = {"gemini-3.5-flash-lite", "gemini-embedding-001"}
    monkeypatch.setattr(settings_api, "client_for", lambda config: FakeProvider(config, known))
    gemini = {
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/",
        "api_key": "gm-key-1234",
        "chat_model": "gemini-3.5-flash-lite",
        "embed_model": "gemini-embedding-001",
    }

    response = client.put("/settings", json=gemini)

    assert response.status_code == 200
    assert response.json()["settings"]["provider"] == "gemini"


def test_settings_survive_restart(settings_env, provider_models, fake_llm):
    from app.main import create_app
    from app.services.llm import get_llm

    app = create_app()
    app.dependency_overrides[get_llm] = lambda: fake_llm
    with TestClient(app) as client:
        client.put("/settings", json=LOCAL)

    with TestClient(create_app()) as restarted:
        assert restarted.get("/settings").json()["provider"] == "custom"


def test_changing_embedding_model_reindexes_without_refetching(client, provider_models, monkeypatch):
    fetches = []

    def fetch_once(url):
        fetches.append(url)
        return FetchedPage(title="Page", text="Saved page text about pricing.")

    monkeypatch.setattr(ingestion, "fetch_url", fetch_once)
    client.post("/ingest", json={"type": "note", "content": "Zebra pricing is per seat."})
    client.post("/ingest", json={"type": "url", "url": "https://example.com/pricing"})
    client.put("/settings", json=OPENAI)

    response = client.put("/settings", json={**OPENAI, "embed_model": "chat-a"})

    assert response.json()["reindexing"] == 2
    assert fetches == ["https://example.com/pricing"]  # stored text reused, page not downloaded again
    assert {item["status"] for item in client.get("/items").json()["items"]} == {"ready"}


def test_same_embedding_model_does_not_reindex(client, provider_models):
    client.post("/ingest", json={"type": "note", "content": "Zebra pricing is per seat."})
    client.put("/settings", json=OPENAI)

    assert client.put("/settings", json={**OPENAI, "chat_model": "chat-a"}).json()["reindexing"] == 0


def test_saving_keeps_tuned_min_score_for_same_provider(client, provider_models, settings_env):
    from app import provider_config
    from app.config import get_settings

    settings_env.setenv("MIN_SCORE", "0.52")  # tuned in .env
    get_settings.cache_clear()
    client.put("/settings", json=OPENAI)
    assert provider_config.load().min_score == 0.52

    client.put("/settings", json=LOCAL)
    assert provider_config.load().min_score == 0.35  # a different provider starts from its default


def test_each_provider_keeps_its_own_key(client, monkeypatch):
    known = {"chat-a", "embed-a", "gemini-3.5-flash-lite", "gemini-embedding-001"}
    monkeypatch.setattr(settings_api, "client_for", lambda config: FakeProvider(config, known))
    gemini = {
        "provider": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/",
        "api_key": "gm-key-1234",
        "chat_model": "gemini-3.5-flash-lite",
        "embed_model": "gemini-embedding-001",
    }
    client.put("/settings", json=OPENAI)
    client.put("/settings", json=gemini)

    # Switching back needs no key: the OpenAI one was kept.
    response = client.put("/settings", json={**OPENAI, "api_key": None})

    assert response.status_code == 200
    body = response.json()["settings"]
    assert body["api_key_hint"] == "••••9876"
    assert body["key_hints"] == {"openai": "••••9876", "gemini": "••••1234"}
    assert "gm-key-1234" not in client.get("/settings").text
