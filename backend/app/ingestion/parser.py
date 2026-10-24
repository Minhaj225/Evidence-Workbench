import re
from pathlib import Path

import pymupdf

from backend.app.chunking.types import SourceBlock
from backend.app.errors import AppError
from backend.app.ingestion.cleaner import clean_blocks


def validate_pdf(path: Path, max_pages: int) -> int:
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise AppError("invalid_pdf", "The file is not a valid PDF.")
    try:
        with pymupdf.open(path) as pdf:
            if pdf.is_encrypted:
                raise AppError("encrypted_pdf", "Password-protected PDFs are not supported.")
            if len(pdf) > max_pages:
                raise AppError("document_page_limit_exceeded", "The PDF exceeds the page limit.")
            if not len(pdf):
                raise AppError("invalid_pdf", "The PDF contains no pages.")
            return len(pdf)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise AppError("invalid_pdf", "The PDF cannot be opened.") from exc


def parse(
    path: Path, document_id: str, media_type: str, max_pages: int = 300
) -> tuple[list[SourceBlock], int]:
    blocks: list[SourceBlock] = []
    if media_type == "text/plain":
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise AppError("unsupported_file_type", "Text files must use UTF-8.") from exc
        if "\x00" in text:
            raise AppError("unsupported_file_type", "Text files must not contain NUL bytes.")
        blocks = [
            SourceBlock(document_id, 1, i, paragraph)
            for i, paragraph in enumerate(re.split(r"\n\s*\n", text))
            if paragraph.strip()
        ]
        page_count = 1
    else:
        page_count = validate_pdf(path, max_pages)
        characters = []
        with pymupdf.open(path) as pdf:
            for page in pdf:
                count = 0
                for item in page.get_text("blocks", sort=True):
                    if item[6] != 0:
                        continue
                    text = item[4]
                    count += sum(not c.isspace() for c in text)
                    blocks.append(
                        SourceBlock(
                            document_id,
                            page.number + 1,
                            item[5],
                            text,
                            tuple(item[:4]),
                            page.rect.width,
                            page.rect.height,
                        )
                    )
                # Include visually nonempty pages even when text extraction returns nothing.
                if count or page.get_images() or page.get_drawings():
                    characters.append(count)
        if sum(characters) < 200 or (
            characters and sum(c < 40 for c in characters) / len(characters) >= 0.8
        ):
            raise AppError(
                "document_requires_ocr",
                "Version 1 supports text-bearing PDFs only; OCR is not supported.",
            )
    blocks = clean_blocks(blocks, page_count)
    if not any(b.kind in {"body", "heading"} and any(c.isalnum() for c in b.text) for b in blocks):
        raise AppError("empty_document", "The document contains no usable text.")
    return blocks, page_count
