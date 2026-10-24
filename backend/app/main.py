import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from backend.app.api import answers, demo, documents, evaluations, health
from backend.app.api.upload_limit import UploadLimit
from backend.app.config import Settings
from backend.app.db import create_database
from backend.app.errors import install_handlers
from backend.app.evaluation.runner import Evaluator
from backend.app.generation.client import Generator
from backend.app.ingestion.service import DocumentService
from backend.app.ingestion.worker import Worker
from backend.app.logging import configure_logging
from backend.app.retrieval.embeddings import Embeddings
from backend.app.retrieval.reranker import Reranker
from backend.app.retrieval.vector_store import VectorStore


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Any = None,
    reranker: Any = None,
    store: Any = None,
    generator: Any = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = app.state
        state.settings = settings
        state.sessions = create_database(settings.database_url)
        state.store = store if store is not None else VectorStore(settings)
        state.embedder, state.reranker = embedder, reranker
        state.generator = generator if generator is not None else Generator(settings)
        state.documents = DocumentService(settings, state.sessions, state.store)
        state.evaluations = Evaluator(state)
        state.worker = None
        try:
            await asyncio.to_thread(state.store.ensure_collections)
            if state.embedder is None:
                state.embedder = await asyncio.to_thread(Embeddings, settings.embedding_model)
            if state.reranker is None:
                state.reranker = await asyncio.to_thread(Reranker, settings.reranker_model)
            state.worker = Worker(state.documents, state.embedder)
            state.worker.evaluation_runner = state.evaluations.run
            state.worker.start()
        except Exception:
            logging.getLogger("rag").error(
                "retrieval_startup_failed", extra={"error_code": "dependency_unavailable"}
            )
        try:
            yield
        finally:
            if state.worker:
                await state.worker.stop()
            await state.generator.close()
            state.store.client.close()
            state.sessions.kw["bind"].dispose()

    app = FastAPI(title="Evaluation-driven document QA", lifespan=lifespan)
    app.add_middleware(UploadLimit, maximum=settings.max_upload_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    install_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request.state.request_id = str(uuid4())
        start = perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        logging.getLogger("rag").info(
            "request_completed",
            extra={
                "request_id": request.state.request_id,
                "duration_ms": (perf_counter() - start) * 1000,
            },
        )
        return response

    for router in (
        health.router,
        documents.router,
        answers.router,
        evaluations.router,
        demo.router,
    ):
        app.include_router(router)
    return app
