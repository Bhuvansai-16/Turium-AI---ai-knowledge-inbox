import io
import sqlite3

import pytest
from docx import Document

from app.services import files

NOTE_TEXT = "Q3 roadmap: launch the citation viewer in August and the Slack connector in September."


def minimal_pdf(text: str) -> bytes:
    """A valid one-page PDF with one line of text, built by hand (objects + xref table)."""
    content = f"BT /F1 18 Tf 20 100 Td ({text}) Tj ET"
    objects = [
        "<</Type/Catalog/Pages 2 0 R>>",
        "<</Type/Pages/Kids[3 0 R]/Count 1>>",
        "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        f"<</Length {len(content)}>>stream\n{content}\nendstream",
        "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    xref_at = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    pdf += f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_at}\n%%EOF\n"
    return pdf.encode()


def docx_bytes(*paragraphs: str) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client, name: str, data: bytes, content_type: str = "application/octet-stream"):
    return client.post("/ingest/file", files={"file": (name, data, content_type)})


def items(client) -> list[dict]:
    return client.get("/items").json()["items"]


@pytest.mark.parametrize(
    "name, data",
    [
        ("roadmap.txt", NOTE_TEXT.encode()),
        ("roadmap.md", f"# Roadmap\n\n{NOTE_TEXT}".encode()),
        ("roadmap.docx", docx_bytes("Roadmap", NOTE_TEXT)),
        ("roadmap.pdf", minimal_pdf("Q3 roadmap launch the citation viewer in August")),
    ],
)
def test_supported_files_are_parsed_and_indexed(client, name, data):
    response = upload(client, name, data)

    assert response.status_code == 202
    body = response.json()
    assert body["source_type"] == "file"
    assert body["title"] == name
    [item] = items(client)
    assert item["status"] == "ready"
    assert item["chunk_count"] >= 1
    assert "citation viewer" in item["preview"]


def test_unsupported_file_type_415(client):
    response = upload(client, "photo.png", b"\x89PNG....")

    assert response.status_code == 415
    error = response.json()["error"]
    assert error["code"] == "unsupported_file_type"
    assert ".pdf" in error["message"]


def test_file_too_large_413(client, monkeypatch):
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 10)

    response = upload(client, "big.txt", b"x" * 11)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_file_without_text_422(client):
    response = upload(client, "empty.txt", b"   \n\n  ")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_text_found"


def test_corrupt_file_422(client):
    response = upload(client, "broken.docx", b"not really a zip file")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable_file"


def test_duplicate_file_409(client):
    upload(client, "roadmap.txt", NOTE_TEXT.encode())

    response = upload(client, "roadmap-copy.txt", NOTE_TEXT.encode())

    assert response.status_code == 409


def test_old_database_is_migrated_to_allow_files(settings_env, tmp_path):
    """Databases created before file support had CHECK (source_type IN ('note', 'url'))."""
    from app import db

    path = tmp_path / "test.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE items (id TEXT PRIMARY KEY, source_type TEXT NOT NULL CHECK (source_type IN ('note', 'url')),
              title TEXT NOT NULL, url TEXT UNIQUE, raw_content TEXT NOT NULL DEFAULT '', content_hash TEXT,
              status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            INSERT INTO items VALUES ('old', 'note', 'Old note', NULL, 'text', 'h', 'ready', NULL, 't', 't');
            """
        )

    db.init_db()

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO items (id, source_type, title, raw_content, status, created_at, updated_at)"
            " VALUES ('new', 'file', 'a.pdf', 'x', 'ready', 't', 't')"
        )
        assert conn.execute("SELECT title FROM items WHERE id = 'old'").fetchone()[0] == "Old note"
