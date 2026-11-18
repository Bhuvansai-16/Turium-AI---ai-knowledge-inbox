from app.services import ingestion
from app.services.fetcher import FetchedPage, FetchError
from app.services.llm import get_llm
from tests.fakes import FakeLLM

NOTE = "Turium builds Zebra\n\nZebra answers questions over enterprise documents with sources."


def items(client) -> list[dict]:
    return client.get("/items").json()["items"]


def stub_fetch(monkeypatch, result):
    def fake_fetch(url):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(ingestion, "fetch_url", fake_fetch)


def test_ingest_note_becomes_ready(client):
    response = client.post("/ingest", json={"type": "note", "content": NOTE})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["source_type"] == "note"

    [item] = items(client)
    assert item["id"] == body["id"]
    assert item["status"] == "ready"
    assert item["title"] == "Turium builds Zebra"
    assert item["chunk_count"] >= 1
    assert item["preview"].startswith("Turium builds Zebra")


def test_note_uses_given_title(client):
    client.post("/ingest", json={"type": "note", "content": NOTE, "title": "Zebra notes"})

    assert items(client)[0]["title"] == "Zebra notes"


def test_duplicate_note_409(client):
    first = client.post("/ingest", json={"type": "note", "content": NOTE}).json()

    response = client.post("/ingest", json={"type": "note", "content": NOTE})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate"
    assert error["details"]["existing_id"] == first["id"]


def test_missing_type_422_envelope(client):
    response = client.post("/ingest", json={"content": "hello"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_blank_note_422(client):
    response = client.post("/ingest", json={"type": "note", "content": "   "})

    assert response.status_code == 422


def test_too_long_note_422(client):
    response = client.post("/ingest", json={"type": "note", "content": "a" * 20_001})

    assert response.status_code == 422


def test_invalid_url_422(client):
    response = client.post("/ingest", json={"type": "url", "url": "not a url"})

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"].startswith("url")


def test_url_ingest_ready(client, monkeypatch):
    stub_fetch(monkeypatch, FetchedPage(title="Zebra launch", text="Zebra is an enterprise assistant."))

    response = client.post("/ingest", json={"type": "url", "url": "https://Example.com/zebra/#top"})

    assert response.status_code == 202
    [item] = items(client)
    assert item["status"] == "ready"
    assert item["title"] == "Zebra launch"
    assert item["url"] == "https://example.com/zebra"


def test_url_without_title_uses_host(client, monkeypatch):
    stub_fetch(monkeypatch, FetchedPage(title=None, text="Plain text page."))

    client.post("/ingest", json={"type": "url", "url": "https://example.com/notes.txt"})

    assert items(client)[0]["title"] == "example.com"


def test_duplicate_url_after_normalization_409(client, monkeypatch):
    stub_fetch(monkeypatch, FetchedPage(title="Zebra", text="Zebra text."))
    client.post("/ingest", json={"type": "url", "url": "https://example.com/zebra"})

    response = client.post("/ingest", json={"type": "url", "url": "https://EXAMPLE.com/zebra/"})

    assert response.status_code == 409


def test_url_fetch_error_marks_failed(client, monkeypatch):
    stub_fetch(monkeypatch, FetchError("The page returned HTTP 404"))

    client.post("/ingest", json={"type": "url", "url": "https://example.com/missing"})

    [item] = items(client)
    assert item["status"] == "failed"
    assert item["error"] == "The page returned HTTP 404"


def test_url_no_text_marks_failed(client, monkeypatch):
    stub_fetch(monkeypatch, FetchedPage(title="SPA", text=""))

    client.post("/ingest", json={"type": "url", "url": "https://example.com/app"})

    [item] = items(client)
    assert item["status"] == "failed"
    assert item["error"] == "No readable text found at this URL"
    assert item["chunk_count"] == 0


def test_failed_duplicate_requeued(client, monkeypatch):
    stub_fetch(monkeypatch, FetchError("The page took too long to respond"))
    first = client.post("/ingest", json={"type": "url", "url": "https://example.com/slow"}).json()
    stub_fetch(monkeypatch, FetchedPage(title="Slow page", text="Finally loaded."))

    response = client.post("/ingest", json={"type": "url", "url": "https://example.com/slow"})

    assert response.status_code == 202
    assert response.json()["id"] == first["id"]
    [item] = items(client)
    assert item["status"] == "ready"
    assert item["error"] is None


def test_long_note_chunks(client):
    paragraphs = [f"Paragraph {i} about topic {i}. " * 6 for i in range(200)]
    content = "\n\n".join(paragraphs)[:20_000]

    client.post("/ingest", json={"type": "note", "content": content})

    [item] = items(client)
    assert item["status"] == "ready"
    assert item["chunk_count"] > 16


def test_provider_error_marks_failed(client):
    client.app.dependency_overrides[get_llm] = lambda: FakeLLM(fail=True)

    client.post("/ingest", json={"type": "note", "content": NOTE})

    [item] = items(client)
    assert item["status"] == "failed"
    assert "AI provider" in item["error"]


def test_ingest_without_provider_503(unconfigured_client):
    response = unconfigured_client.post("/ingest", json={"type": "note", "content": NOTE})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"


def test_concurrent_duplicate_url_409(client, monkeypatch):
    """Two requests for one URL can both pass the duplicate check; the UNIQUE index must turn
    the loser into a 409, not a 500."""
    stub_fetch(monkeypatch, FetchedPage(title="Zebra", text="Zebra text."))
    client.post("/ingest", json={"type": "url", "url": "https://example.com/race"})
    monkeypatch.setattr(ingestion.repository, "find_duplicate", lambda conn, **kwargs: None)

    response = client.post("/ingest", json={"type": "url", "url": "https://example.com/race"})

    assert response.status_code == 409
    assert response.json()["error"]["details"]["existing_id"]


def test_item_deleted_during_processing_leaves_no_orphans(client, fake_llm):
    original_embed = fake_llm.embed

    def embed_then_delete(texts):
        [item] = items(client)
        client.delete(f"/items/{item['id']}")
        return original_embed(texts)

    fake_llm.embed = embed_then_delete

    client.post("/ingest", json={"type": "note", "content": NOTE})

    from app import db

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    assert items(client) == []


def test_items_empty(client):
    assert client.get("/items").json() == {"items": []}
