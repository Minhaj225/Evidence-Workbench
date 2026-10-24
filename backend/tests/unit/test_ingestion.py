import io

import pymupdf
import pytest
from fastapi import UploadFile

from backend.app.chunking.types import SourceBlock
from backend.app.errors import AppError
from backend.app.ingestion.cleaner import clean_blocks, normalize
from backend.app.ingestion.parser import parse, validate_pdf
from backend.app.ingestion.storage import original_path, sanitize_filename, stage_upload


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../../private.pdf", "private.pdf"),
        (r"C:\files\name.txt", "name.txt"),
        ("bad\x00\nname.PDF", "badname.pdf"),
        ("", "document"),
    ],
)
def test_sanitization(name, expected):
    assert sanitize_filename(name) == expected
    assert len(sanitize_filename("a" * 400 + ".pdf")) == 180


def test_normalization():
    assert (
        normalize("caf\u0065\u0301\u00a0  data\r\n\r\nre-\nsponsible") == "café data\n\nresponsible"
    )
    assert normalize("risk-based\nPolicy") == "risk-based\nPolicy"
    assert normalize("ISO-\n9000") == "ISO-\n9000"


def test_headers_footers_and_provenance():
    blocks = []
    for page in range(1, 6):
        blocks.extend(
            [
                SourceBlock("doc", page, 0, f"Page {page}", (0, 0, 40, 20), 600, 800),
                SourceBlock(
                    "doc",
                    page,
                    1,
                    "A meaningful paragraph about risk management.",
                    (0, 200, 400, 300),
                    600,
                    800,
                ),
                SourceBlock("doc", page, 2, "NIST publication", (0, 760, 400, 790), 600, 800),
            ]
        )
    cleaned = clean_blocks(blocks, 5)
    assert [b.kind for b in cleaned] == ["header", "body", "footer"] * 5
    assert all(a.source_end < b.source_start for a, b in zip(cleaned, cleaned[1:], strict=False))


def test_text_and_pdf_parse(text_file, document_id, tmp_path, pdf_bytes):
    blocks, pages = parse(text_file, document_id, "text/plain")
    assert pages == 1 and blocks[0].kind == "heading"
    assert all(b.source_end - b.source_start == len(b.text) for b in blocks)
    path = tmp_path / "test.pdf"
    path.write_bytes(pdf_bytes)
    blocks, pages = parse(path, document_id, "application/pdf")
    assert pages == 1 and blocks[0].bbox is not None
    assert "GOVERN" in blocks[0].text


def test_pdf_validation(tmp_path, document_id):
    path = tmp_path / "test.pdf"
    path.write_bytes(b"invalid")
    with pytest.raises(AppError, match="invalid_pdf"):
        validate_pdf(path, 300)
    with pymupdf.open() as pdf:
        pdf.new_page()
        path.write_bytes(pdf.tobytes())
        with pytest.raises(AppError, match="document_requires_ocr"):
            parse(path, document_id, "application/pdf")
        path.write_bytes(
            pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="a", user_pw="b")
        )
        with pytest.raises(AppError, match="encrypted_pdf"):
            validate_pdf(path, 300)
        pdf.new_page()
        path.write_bytes(pdf.tobytes())
        with pytest.raises(AppError, match="document_page_limit_exceeded"):
            validate_pdf(path, 1)


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("a.txt", b"", "empty_document"),
        ("a.zip", b"abc", "unsupported_file_type"),
        ("a.txt", b"bad\xff", "unsupported_file_type"),
        ("a.txt", b"a\x00b", "unsupported_file_type"),
        ("a.pdf", b"not pdf", "invalid_pdf"),
    ],
)
async def test_bad_upload_cleanup(settings, name, data, code):
    with pytest.raises(AppError, match=code):
        await stage_upload(UploadFile(filename=name, file=io.BytesIO(data)), settings)
    assert not list(settings.document_root.iterdir())


async def test_upload_size_and_path(settings, document_id):
    settings.max_upload_bytes = 3
    with pytest.raises(AppError, match="upload_too_large"):
        await stage_upload(UploadFile(filename="a.txt", file=io.BytesIO(b"four")), settings)
    assert not list(settings.document_root.iterdir())
    assert original_path(settings, document_id, "text/plain").name == "original.txt"
    with pytest.raises(ValueError):
        original_path(settings, "../../x", "text/plain")
