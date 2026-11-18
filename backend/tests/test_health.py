def test_health_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["llm_configured"] is False


def test_health_reports_models(client, settings_env):
    from app.config import get_settings

    settings_env.setenv("CHAT_MODEL", "acme/chat-1")
    settings_env.setenv("EMBED_MODEL", "acme/embed-1")
    get_settings.cache_clear()

    body = client.get("/health").json()

    assert body["chat_model"] == "acme/chat-1"
    assert body["embed_model"] == "acme/embed-1"


def test_request_id_echoed(client):
    response = client.get("/health", headers={"X-Request-ID": "abc"})

    assert response.headers["X-Request-ID"] == "abc"


def test_request_id_generated_when_missing(client):
    response = client.get("/health")

    assert len(response.headers["X-Request-ID"]) == 32


def test_unhandled_error_has_request_id(settings_env):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["X-Request-ID"] == "req-500"
    assert "kaboom" not in response.text


def test_unknown_route_uses_envelope(client):
    response = client.get("/nope", headers={"X-Request-ID": "req-1"})

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == "req-1"
