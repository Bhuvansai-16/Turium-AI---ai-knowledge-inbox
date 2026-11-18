import time

from fastapi.testclient import TestClient

from app import db, repository
from app.services.llm import get_llm
from tests.fakes import FakeLLM


def seed_stuck_item() -> str:
    db.init_db()
    with db.connect() as conn:
        item_id = repository.create_item(
            conn, source_type="note", title="Left over", url=None, raw_content="Interrupted note text.", content_hash="x"
        )
        repository.set_status(conn, item_id, "processing")
    return item_id


def wait_for_status(client: TestClient, wanted: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        [item] = client.get("/items").json()["items"]
        if item["status"] == wanted or time.monotonic() > deadline:
            return item
        time.sleep(0.05)


def test_stuck_items_requeued(settings_env):
    from app.main import create_app

    item_id = seed_stuck_item()
    app = create_app()
    app.dependency_overrides[get_llm] = lambda: FakeLLM()

    with TestClient(app) as client:
        item = wait_for_status(client, "ready")

    assert item["id"] == item_id
    assert item["status"] == "ready"


def test_stuck_items_fail_without_provider(settings_env):
    from app.main import create_app

    seed_stuck_item()

    with TestClient(create_app()) as client:
        [item] = client.get("/items").json()["items"]

    assert item["status"] == "failed"
    assert "Settings" in item["error"]
