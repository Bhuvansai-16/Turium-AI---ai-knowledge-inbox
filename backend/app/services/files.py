"""Turn uploaded documents into plain text, which is then indexed exactly like a note.

Extraction runs inside the upload request: it is CPU-only and bounded by the size cap, so
the request still returns quickly, and an unreadable file fails immediately with a clear
error instead of a "failed" item appearing later. Embedding stays in the background.
"""

import io
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import AppError

MAX_FILE_BYTES = 10 * 1024 * 1024
SUPPORTED = (".pdf", ".docx", ".txt", ".md", ".markdown")


def check_size(size: int) -> None:
    if size > MAX_FILE_BYTES:
        raise AppError(413, "file_too_large", f"Files can be up to {MAX_FILE_BYTES // (1024 * 1024)} MB")


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise AppError(
            415,
            "unsupported_file_type",
            f"Can't read {suffix or 'this'} files. Supported: {', '.join(SUPPORTED)}",
        )

    try:
        if suffix == ".pdf":
            pages = PdfReader(io.BytesIO(data)).pages
            text = "\n\n".join(page.extract_text() or "" for page in pages)
        elif suffix == ".docx":
            text = "\n\n".join(paragraph.text for paragraph in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8-sig", errors="replace")
    except (PdfReadError, BadZipFile, ValueError, KeyError, OSError) as exc:
        # A .docx is a zip archive, so a damaged one fails as BadZipFile; pypdf raises its own errors.
        raise AppError(422, "unreadable_file", "This file looks damaged or isn't really a " + suffix) from exc

    text = text.strip()
    if not text:
        raise AppError(
            422,
            "no_text_found",
            "Couldn't find any text in this file. Scanned PDFs need OCR, which isn't supported.",
        )
    return text
