import asyncio
import io
from unittest.mock import patch

import pytest
from fastapi import UploadFile

from backend.app.db import create_database
from backend.app.errors import AppError
from backend.app.ingestion.service import DocumentService
from backend.app.ingestion.worker import Worker
from backend.app.models import Document, IngestionJob


async def test_partial_index_cleanup_retry_and_recovery(settings, store, embedder):
    sessions = create_database(settings.database_url)
    service = DocumentService(settings, sessions, store)
    service.accepting = True

    def upload():
        return UploadFile(filename="sample.txt", file=io.BytesIO(b"Govern means setting policy."))

    response, _ = await service.upload(upload(), False)
    doc_id, job_id = response["document"]["id"], response["job"]["id"]
    worker = Worker(service, embedder)
    original_index = store.index

    def interrupted(strategy, chunks, vectors, title):
        original_index(strategy, chunks, vectors, title)
        raise RuntimeError("A simulated partial write")

    with patch.object(store, "index", side_effect=interrupted):
        await worker.process(job_id)
    assert store.count("baseline", doc_id) == store.count("semantic", doc_id) == 0
    with sessions() as session:
        assert session.get(Document, doc_id).status == "failed"
    retried, status = await service.upload(upload(), True)
    assert status == 202
    job_id = retried["job"]["id"]
    with sessions() as session:
        session.get(IngestionJob, job_id).status = "running"
        session.get(Document, doc_id).status = "processing"
        session.commit()
    worker.recover()
    await worker.process(job_id)
    with sessions() as session:
        assert session.get(Document, doc_id).status == "ready"
        assert session.get(IngestionJob, job_id).attempt == 2
    sessions.kw["bind"].dispose()


async def test_delete_partial_cleanup_and_force_lock(settings, store, embedder):
    sessions = create_database(settings.database_url)
    service = DocumentService(settings, sessions, store)
    service.accepting = True
    response, _ = await service.upload(
        UploadFile(filename="a.txt", file=io.BytesIO(b"Text.")), False
    )
    doc_id = response["document"]["id"]
    async with service.lock(doc_id):
        with pytest.raises(AppError, match="document_processing"):
            await service.delete(doc_id, False)
        deletion = asyncio.create_task(service.delete(doc_id, True))
        await asyncio.sleep(0.01)
        assert not deletion.done()
    await deletion
    with sessions() as session:
        assert session.get(Document, doc_id) is None
    response, _ = await service.upload(
        UploadFile(filename="a.txt", file=io.BytesIO(b"Other.")), False
    )
    doc_id = response["document"]["id"]
    with patch.object(store, "delete", side_effect=RuntimeError("failure")):
        with pytest.raises(AppError, match="deletion_failed"):
            await service.delete(doc_id, False)
    with sessions() as session:
        assert session.get(Document, doc_id).status == "deleting"
    await service.delete(doc_id, False)
    sessions.kw["bind"].dispose()
