from app.services import ingestion
from app.services.fetcher import FetchedPage, FetchError

NOTE = "Vendor contract: Acme renewal is due on 14 March 2027."


def add_note(client, content: str = NOTE) -> str:
    return client.post("/ingest", json={"type": "note", "content": content}).json()["id"]


def items(client) -> list[dict]:
    return client.get("/items").json()["items"]


def test_delete_item_removes_it(client):
    item_id = add_note(client)

    response = client.delete(f"/items/{item_id}")

    assert response.status_code == 204
    assert items(client) == []


def test_deleted_item_no_longer_answers(client):
    item_id = add_note(client)
    client.delete(f"/items/{item_id}")

    body = client.post("/query", json={"question": "When is the Acme renewal?"}).json()

    assert body["sources"] == []


def test_delete_missing_item_404(client):
    response = client.delete("/items/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "item_not_found"


def test_retry_failed_item(client, monkeypatch):
    monkeypatch.setattr(ingestion, "fetch_url", lambda url: (_ for _ in ()).throw(FetchError("timed out")))
    item_id = client.post("/ingest", json={"type": "url", "url": "https://example.com/a"}).json()["id"]
    assert items(client)[0]["status"] == "failed"
    monkeypatch.setattr(ingestion, "fetch_url", lambda url: FetchedPage(title="A", text="Recovered text."))

    response = client.post(f"/items/{item_id}/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    [item] = items(client)
    assert item["status"] == "ready"
    assert item["error"] is None


def test_retry_ready_item_409(client):
    item_id = add_note(client)

    response = client.post(f"/items/{item_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_retryable"


def test_retry_missing_item_404(client):
    assert client.post("/items/nope/retry").status_code == 404
