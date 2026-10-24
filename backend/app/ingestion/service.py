import asyncio
import os
import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.app.chunking import baseline, semantic
from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.ingestion.storage import original_path, stage_upload
from backend.app.models import Document, IngestionJob, new_id


def latest_job(session: Any, document_id: str) -> IngestionJob | None:
    return session.scalar(
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )


def public_record(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    values = {column.name: getattr(record, column.name) for column in record.__table__.columns}
    return {
        key: value.replace(tzinfo=UTC)
        if isinstance(value, datetime) and value.tzinfo is None
        else value
        for key, value in values.items()
    }


def document_record(session: Any, document: Document) -> dict[str, Any]:
    return {
        "document": public_record(document),
        "job": public_record(latest_job(session, document.id)),
    }


class DocumentService:
    def __init__(self, settings: Settings, sessions: Any, store: Any):
        self.settings, self.sessions, self.store = settings, sessions, store
        self.mutations = asyncio.Lock()
        self.document_locks: dict[str, asyncio.Lock] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.accepting = False

    def lock(self, document_id: str) -> asyncio.Lock:
        return self.document_locks.setdefault(document_id, asyncio.Lock())

    async def upload(self, upload: Any, retry_failed: bool) -> tuple[dict[str, Any], int]:
        if not self.accepting:
            raise AppError("worker_unavailable", "Document processing is unavailable.", 503)
        try:
            await asyncio.to_thread(self.store.ping)
        except Exception as exc:
            raise AppError(
                "vector_store_unavailable", "Vector storage is unavailable.", 503
            ) from exc
        temporary, digest, name, size, media_type = await stage_upload(upload, self.settings)
        try:
            async with self.mutations:
                if not self.accepting:
                    raise AppError("worker_unavailable", "Document processing is unavailable.", 503)
                with self.sessions() as session:
                    document = session.scalar(select(Document).where(Document.sha256 == digest))
                    if document:
                        if document.status == "deleting":
                            raise AppError(
                                "document_deleting",
                                "Finish deleting this document before uploading it.",
                                409,
                            )
                        stale = document.status == "ready" and (
                            document.baseline_chunker_version != baseline.VERSION
                            or document.semantic_chunker_version != semantic.VERSION
                            or document.embedding_model != self.settings.embedding_model
                        )
                        if document.status == "ready" and not stale:
                            stale = any(
                                [
                                    await asyncio.to_thread(self.store.count, strategy, document.id)
                                    != expected
                                    for strategy, expected in (
                                        ("baseline", document.baseline_chunk_count),
                                        ("semantic", document.semantic_chunk_count),
                                    )
                                ]
                            )
                        if document.status == "failed" or stale:
                            if self.lock(document.id).locked():
                                raise AppError("document_busy", "The document is in use.", 409)
                            if document.status == "failed" and not retry_failed:
                                raise AppError(
                                    "retry_required", "Retry the failed document explicitly.", 409
                                )
                            previous = latest_job(session, document.id)
                            document.status = "queued"
                            document.error_code = document.error_message = None
                            job = IngestionJob(
                                document_id=document.id,
                                attempt=(previous.attempt + 1 if previous else 1),
                            )
                            session.add(job)
                            session.commit()
                            self.queue.put_nowait(job.id)
                            return {**document_record(session, document), "deduplicated": True}, 202
                        return {**document_record(session, document), "deduplicated": True}, (
                            200 if document.status == "ready" else 202
                        )
                    document = Document(
                        id=new_id(),
                        sha256=digest,
                        original_filename=name,
                        byte_size=size,
                        media_type=media_type,
                        status="queued",
                    )
                    target = original_path(self.settings, document.id, media_type)
                    target.parent.mkdir(mode=0o700)
                    try:
                        os.replace(temporary, target)
                        session.add(document)
                        session.flush()
                        job = IngestionJob(document_id=document.id)
                        session.add(job)
                        session.commit()
                    except BaseException:
                        session.rollback()
                        shutil.rmtree(target.parent)
                        raise
                    self.queue.put_nowait(job.id)
                    return {**document_record(session, document), "deduplicated": False}, 202
        finally:
            temporary.unlink(missing_ok=True)

    async def delete(self, document_id: str, force: bool) -> None:
        lock = self.lock(document_id)
        if lock.locked() and not force:
            raise AppError(
                "document_processing", "The document is processing; wait or use force=true.", 409
            )
        # Force waits for indexing to release its lock, preventing vectors from reappearing.
        async with lock, self.mutations:
            with self.sessions() as session:
                document = session.get(Document, document_id)
                if not document:
                    raise AppError("document_not_found", "Document not found.", 404)
                document.status = "deleting"
                session.commit()
                try:
                    await asyncio.to_thread(self.store.delete, document_id)
                    source = original_path(self.settings, document_id, document.media_type)
                    if source.parent.exists():
                        await asyncio.to_thread(shutil.rmtree, source.parent)
                    cached = self.settings.page_cache_root / document_id
                    if cached.exists():
                        await asyncio.to_thread(shutil.rmtree, cached)
                except Exception as exc:
                    document.error_code = "deletion_failed"
                    document.error_message = "Cleanup is incomplete; retry deletion."
                    session.commit()
                    raise AppError("deletion_failed", document.error_message, 503) from exc
                session.delete(document)
                session.commit()
