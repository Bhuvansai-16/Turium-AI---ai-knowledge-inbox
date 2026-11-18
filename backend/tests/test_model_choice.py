import json

import pytest

from app.api import settings as settings_api
from app.config import get_settings
from tests.fakes import FakeProvider

ZEBRA = "Turium builds Zebra.\n\nZebra answers enterprise questions with cited sources."
SETTINGS = {
    "provider": "openai",
    "base_url": "https://api.openai.com/v1/",
    "api_key": "sk-secret-key-9876",
    "chat_model": "chat-a",
    "chat_models": ["chat-a", "chat-b"],
    "embed_model": "embed-a",
}


@pytest.fixture(autouse=True)
def setup(settings_env, monkeypatch):
    settings_env.setenv("MIN_SCORE", "0.1")
    get_settings.cache_clear()
    known = {"chat-a", "chat-b", "chat-c", "embed-a"}
    monkeypatch.setattr(settings_api, "client_for", lambda config: FakeProvider(config, known))


def done_event(response) -> dict:
    blocks = [block for block in response.text.strip().split("\n\n") if block.startswith("event: done")]
    return json.loads(blocks[-1].split("data: ", 1)[1])


def test_settings_store_enabled_chat_models(client):
    saved = client.put("/settings", json=SETTINGS).json()["settings"]

    assert saved["chat_models"] == ["chat-a", "chat-b"]
    assert client.get("/settings").json()["chat_models"] == ["chat-a", "chat-b"]


def test_default_model_is_always_enabled(client):
    saved = client.put("/settings", json={**SETTINGS, "chat_models": ["chat-b"]}).json()["settings"]

    assert saved["chat_models"] == ["chat-a", "chat-b"]


def test_enabled_models_must_exist(client):
    response = client.put("/settings", json={**SETTINGS, "chat_models": ["chat-a", "made-up"]})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "model_not_found"


def test_question_can_pick_an_enabled_model(client):
    client.put("/settings", json=SETTINGS)
    client.post("/ingest", json={"type": "note", "content": ZEBRA})

    response = client.post("/query/stream", json={"question": "What does Turium build with Zebra?", "model": "chat-b"})

    assert done_event(response)["meta"]["model"] == "chat-b"


def test_model_that_is_not_enabled_is_rejected(client):
    client.put("/settings", json=SETTINGS)

    response = client.post("/query/stream", json={"question": "What does Turium build?", "model": "chat-c"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "model_not_enabled"
