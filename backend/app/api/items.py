from fastapi import APIRouter, BackgroundTasks, Depends, Response

from app import db, repository
from app.errors import AppError
from app.schemas import ItemList, ItemOut
from app.services import ingestion
from app.services.llm import LLMClient, get_llm

router = APIRouter()


def _not_found(item_id: str) -> AppError:
    return AppError(404, "item_not_found", "No item with this id", {"item_id": item_id})


@router.get("/items", response_model=ItemList)
def list_items() -> ItemList:
    """All saved items, newest first, with processing status."""
    with db.connect() as conn:
        rows = repository.list_items(conn)
    return ItemList(items=[ItemOut.from_row(row) for row in rows])


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: str) -> Response:
    """Remove an item and all of its chunks."""
    with db.connect() as conn:
        if not repository.delete_item(conn, item_id):
            raise _not_found(item_id)
    return Response(status_code=204)


@router.post("/items/{item_id}/retry", status_code=202, response_model=ItemOut)
def retry_item(item_id: str, background: BackgroundTasks, llm: LLMClient = Depends(get_llm)) -> ItemOut:
    """Re-run ingestion for a failed item (e.g. a URL that timed out)."""
    with db.connect() as conn:
        item = repository.get_item(conn, item_id)
        if item is None:
            raise _not_found(item_id)
        if item["status"] != "failed":
            raise AppError(409, "not_retryable", "Only failed items can be retried", {"status": item["status"]})
        repository.reset_for_retry(conn, item_id)
        item = repository.get_item(conn, item_id)

    background.add_task(ingestion.run_ingestion, item_id, llm)
    return ItemOut.from_row(item)
