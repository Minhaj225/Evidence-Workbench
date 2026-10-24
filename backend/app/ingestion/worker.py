import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select

from backend.app.chunking import baseline, semantic
from backend.app.errors import AppError
from backend.app.ingestion.cleaner import PARSER_VERSION
from backend.app.ingestion.parser import parse
from backend.app.ingestion.service import DocumentService
from backend.app.ingestion.storage import original_path
from backend.app.models import Document, EvaluationRun, IngestionJob, now

logger = logging.getLogger("rag")


class Worker:
    def __init__(self, service: DocumentService, embedder: Any):
        self.service, self.embedder = service, embedder
        self.task: asyncio.Task[None] | None = None
        self.stopping = False
        self.evaluation_runner: Callable[[str], Awaitable[None]] | None = None

    def recover(self) -> None:
        with self.service.sessions() as session:
            jobs = session.scalars(
                select(IngestionJob)
                .where(IngestionJob.status.in_(["queued", "running"]))
                .order_by(IngestionJob.created_at)
            ).all()
            for job in jobs:
                document = session.get(Document, job.document_id)
                if document and document.status != "deleting":
                    job.status, document.status = "queued", "queued"
                    self.service.queue.put_nowait(job.id)
            session.commit()
            for run in session.scalars(
                select(EvaluationRun).where(EvaluationRun.status.in_(["queued", "running"]))
            ):
                run.status = "queued"
                self.service.queue.put_nowait("evaluation:" + run.id)
            session.commit()

    def start(self) -> None:
        self.recover()
        self.stopping = False
        self.service.accepting = True
        self.task = asyncio.create_task(self.run())

    def stage(self, job_id: str, stage: str) -> None:
        with self.service.sessions() as session:
            job = session.get(IngestionJob, job_id)
            if job:
                job.stage = stage
                session.commit()
                logger.info("ingestion_stage", extra={"job_id": job_id, "stage": stage})

    async def process(self, job_id: str) -> None:
        with self.service.sessions() as session:
            job = session.get(IngestionJob, job_id)
            if not job or job.status != "queued":
                return
            document_id = job.document_id
        async with self.service.lock(document_id):
            with self.service.sessions() as session:
                document = session.get(Document, document_id)
                job = session.get(IngestionJob, job_id)
                if not document or not job or document.status != "queued":
                    return
                document.status, job.status, job.started_at = "processing", "running", now()
                session.commit()
                path = original_path(self.service.settings, document.id, document.media_type)
                digest, title, media_type = (
                    document.sha256,
                    document.original_filename,
                    document.media_type,
                )
            try:
                await asyncio.to_thread(self.service.store.delete, document_id)
                self.stage(job_id, "parse")
                blocks, pages = await asyncio.to_thread(
                    parse, path, document_id, media_type, self.service.settings.max_pdf_pages
                )
                self.stage(job_id, "chunk")
                fixed = await asyncio.to_thread(
                    baseline.chunk, blocks, digest, self.embedder.tokenizer
                )
                enhanced = await asyncio.to_thread(
                    semantic.chunk, blocks, digest, self.embedder.tokenizer, self.embedder
                )
                for strategy, chunks in (("baseline", fixed), ("semantic", enhanced)):
                    self.stage(job_id, "embed")
                    vectors = await asyncio.to_thread(
                        self.embedder.embed_documents, [c.text for c in chunks]
                    )
                    self.stage(job_id, "index")
                    await asyncio.to_thread(
                        self.service.store.index, strategy, chunks, vectors, title
                    )
                    count = await asyncio.to_thread(self.service.store.count, strategy, document_id)
                    if count != len(chunks):
                        raise AppError(
                            "index_verification_failed",
                            "The stored chunk count could not be verified.",
                            503,
                        )
                self.stage(job_id, "finalize")
                with self.service.sessions() as session:
                    document = session.get(Document, document_id)
                    job = session.get(IngestionJob, job_id)
                    assert document and job
                    document.status, document.page_count, document.ready_at = "ready", pages, now()
                    document.baseline_chunk_count, document.semantic_chunk_count = (
                        len(fixed),
                        len(enhanced),
                    )
                    document.parser_version = PARSER_VERSION
                    document.baseline_chunker_version = baseline.VERSION
                    document.semantic_chunker_version = semantic.VERSION
                    document.embedding_model = self.service.settings.embedding_model
                    job.status, job.completed_at = "completed", now()
                    session.commit()
            except asyncio.CancelledError:
                with self.service.sessions() as session:
                    document = session.get(Document, document_id)
                    job = session.get(IngestionJob, job_id)
                    if document and job:
                        document.status = job.status = "queued"
                        session.commit()
                raise
            except Exception as exc:
                code = exc.code if isinstance(exc, AppError) else "ingestion_failed"
                message = (
                    exc.message
                    if isinstance(exc, AppError)
                    else "Document processing failed; retry ingestion."
                )
                try:
                    await asyncio.to_thread(self.service.store.delete, document_id)
                except Exception:
                    code, message = (
                        "index_cleanup_failed",
                        "Index cleanup failed; retry ingestion to remove partial points.",
                    )
                with self.service.sessions() as session:
                    document = session.get(Document, document_id)
                    job = session.get(IngestionJob, job_id)
                    assert document and job
                    document.status = job.status = "failed"
                    document.error_code = job.error_code = code
                    document.error_message = job.error_message = message
                    job.completed_at = now()
                    session.commit()
                logger.error("ingestion_failed", extra={"job_id": job_id, "error_code": code})

    async def run(self) -> None:
        try:
            while not self.stopping:
                try:
                    job_id = await asyncio.wait_for(self.service.queue.get(), timeout=1)
                except TimeoutError:
                    continue
                try:
                    if job_id.startswith("evaluation:") and self.evaluation_runner:
                        await self.evaluation_runner(job_id.removeprefix("evaluation:"))
                    else:
                        await self.process(job_id)
                finally:
                    self.service.queue.task_done()
        finally:
            self.service.accepting = False

    async def stop(self) -> None:
        self.service.accepting = False
        self.stopping = True
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=30)
            except TimeoutError:
                # Interrupted native calls cannot mark ready; startup deletes their partial index.
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
