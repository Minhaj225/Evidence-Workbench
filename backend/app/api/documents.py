import asyncio
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID

import pymupdf
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from backend.app.errors import AppError
from backend.app.ingestion.service import document_record
from backend.app.ingestion.storage import original_path
from backend.app.models import Document

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(request: Request) -> list[dict]:
    with request.app.state.sessions() as session:
        return [
            document_record(session, d)
            for d in session.scalars(select(Document).order_by(Document.created_at.desc()))
        ]


@router.post("")
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    retry_failed: Annotated[bool, Form()] = False,
) -> JSONResponse:
    result, status = await request.app.state.documents.upload(file, retry_failed)
    return JSONResponse(jsonable_encoder(result), status_code=status)


@router.get("/{document_id}")
def get_document(document_id: UUID, request: Request) -> dict:
    with request.app.state.sessions() as session:
        document = session.get(Document, str(document_id))
        if not document:
            raise AppError("document_not_found", "Document not found.", 404)
        return document_record(session, document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, request: Request, force: bool = False) -> Response:
    await request.app.state.documents.delete(str(document_id), force)
    return Response(status_code=204)


def render_page(source: Path, target: Path, number: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".tmp")
    try:
        with pymupdf.open(source) as pdf:
            pixmap = pdf[number - 1].get_pixmap(dpi=144)
            temporary.write_bytes(pixmap.tobytes("png"))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


@router.get("/{document_id}/pages/{page_number}")
async def page_preview(document_id: UUID, page_number: int, request: Request) -> Response:
    state, doc_id = request.app.state, str(document_id)
    async with state.documents.lock(doc_id):
        with state.sessions() as session:
            document = session.get(Document, doc_id)
            if not document:
                raise AppError("document_not_found", "Document not found.", 404)
            if document.status != "ready":
                raise AppError("document_not_ready", "The document is not ready.", 409)
            if document.media_type != "application/pdf":
                raise AppError("page_not_supported", "Text documents do not have page previews.")
            if not 1 <= page_number <= (document.page_count or 0):
                raise AppError("invalid_page", "Page number is out of bounds.")
            target = (
                state.settings.page_cache_root / doc_id / f"{document.sha256}-{page_number}-v1.png"
            )
            if not target.exists():
                await asyncio.to_thread(
                    render_page,
                    original_path(state.settings, doc_id, document.media_type),
                    target,
                    page_number,
                )
        # Read while holding the document lock so deletion cannot race response streaming.
        data = await asyncio.to_thread(target.read_bytes)
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
