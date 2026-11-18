from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile

from app import db, repository
from app.errors import AppError
from app.schemas import IngestRequest, ItemOut
from app.services import files, ingestion
from app.services.llm import LLMClient, get_llm

router = APIRouter()


@router.post("/ingest", status_code=202, response_model=ItemOut)
def ingest(request: IngestRequest, background: BackgroundTasks, llm: LLMClient = Depends(get_llm)) -> ItemOut:
    """Accept a note or URL and index it in the background. Poll GET /items for its status."""
    return _accept(lambda conn: ingestion.submit(conn, request), background, llm)


@router.post("/ingest/file", status_code=202, response_model=ItemOut)
def ingest_file(file: UploadFile, background: BackgroundTasks, llm: LLMClient = Depends(get_llm)) -> ItemOut:
    """Upload a PDF, Word (.docx), text or Markdown file. Its text is extracted now and indexed
    in the background, exactly like a note."""
    data = file.file.read(files.MAX_FILE_BYTES + 1)
    files.check_size(len(data))
    text = files.extract_text(file.filename or "upload", data)
    return _accept(lambda conn: ingestion.submit_file(conn, file.filename or "upload", text), background, llm)


def _accept(submit, background: BackgroundTasks, llm: LLMClient) -> ItemOut:
    try:
        with db.connect() as conn:
            item_id = submit(conn)
            item = repository.get_item(conn, item_id)
    except ingestion.DuplicateItemError as exc:
        raise AppError(409, "duplicate", "This item is already in your inbox", {"existing_id": exc.existing_id})

    background.add_task(ingestion.run_ingestion, item_id, llm)
    return ItemOut.from_row(item)
