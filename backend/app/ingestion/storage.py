import hashlib
import os
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.ingestion.parser import validate_pdf


def sanitize_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        c for c in unicodedata.normalize("NFC", name) if not unicodedata.category(c).startswith("C")
    ).strip()
    suffix = Path(name).suffix.lower()
    stem = name[: -len(suffix)] if suffix else name
    return (stem[: 180 - len(suffix)] + suffix) or "document"


async def stage_upload(upload: Any, settings: Settings) -> tuple[Path, str, str, int, str]:
    settings.document_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=settings.document_root)
    path = Path(temporary)
    try:
        digest, size = hashlib.sha256(), 0
        with os.fdopen(fd, "wb") as stream:
            while data := await upload.read(65536):
                size += len(data)
                if size > settings.max_upload_bytes:
                    raise AppError(
                        "upload_too_large", "The file exceeds the upload size limit.", 413
                    )
                digest.update(data)
                stream.write(data)
        if not size:
            raise AppError("empty_document", "The uploaded file is empty.")
        name = sanitize_filename(upload.filename or "document")
        extension = Path(name).suffix.lower()
        if extension == ".pdf":
            import asyncio

            await asyncio.to_thread(validate_pdf, path, settings.max_pdf_pages)
            media_type = "application/pdf"
        elif extension == ".txt":
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise AppError("unsupported_file_type", "Text files must use UTF-8.") from exc
            if "\x00" in text:
                raise AppError("unsupported_file_type", "Text files must not contain NUL bytes.")
            media_type = "text/plain"
        else:
            raise AppError("unsupported_file_type", "Upload a PDF or UTF-8 .txt file.", 415)
        return path, digest.hexdigest(), name, size, media_type
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def original_path(settings: Settings, document_id: str, media_type: str) -> Path:
    from uuid import UUID

    canonical = str(UUID(document_id))
    return (
        settings.document_root
        / canonical
        / ("original.pdf" if media_type == "application/pdf" else "original.txt")
    )
