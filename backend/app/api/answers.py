from time import perf_counter

from fastapi import APIRouter, Request
from sqlalchemy import select

from backend.app.errors import AppError
from backend.app.generation.prompts import VERSION
from backend.app.models import Document
from backend.app.retrieval.service import retrieve
from backend.app.schemas import AnswerRequest

router = APIRouter(prefix="/api/answers", tags=["answers"])


@router.post("")
async def answer_question(body: AnswerRequest, request: Request) -> dict:
    start, state = perf_counter(), request.app.state
    if not state.embedder or not state.reranker:
        raise AppError("model_unavailable", "Local retrieval models are unavailable.", 503)
    if len(body.question) > state.settings.max_question_chars:
        raise AppError("invalid_question", "The question exceeds the configured limit.")
    ids = list(dict.fromkeys(str(doc_id) for doc_id in body.document_ids))
    if len(ids) > state.settings.max_selected_documents:
        raise AppError("invalid_question", "Too many documents selected.")
    with state.sessions() as session:
        if ids:
            for doc_id in ids:
                document = session.get(Document, doc_id)
                if not document:
                    raise AppError("document_not_found", "A selected document does not exist.", 404)
                if document.status != "ready":
                    raise AppError("document_not_ready", "A selected document is not ready.", 409)
        else:
            ids = list(session.scalars(select(Document.id).where(Document.status == "ready")))
    if not ids:
        raise AppError(
            "no_ready_documents", "Upload a document and wait for processing first.", 409
        )
    sources, timings = await retrieve(
        body.question, ids, body.strategy, state.embedder, state.reranker, state.store
    )
    generation_start = perf_counter()
    generated, usage = await state.generator.answer(body.question, sources)
    timings["generation"] = (perf_counter() - generation_start) * 1000
    timings["total"] = (perf_counter() - start) * 1000
    return {
        "request_id": request.state.request_id,
        "answer": generated.answer,
        "insufficient_context": generated.insufficient_context,
        "strategy": body.strategy,
        "citations": [
            s.citation.model_dump(mode="json")
            for s in sources
            if s.citation.source_id in generated.used_source_ids
        ],
        "timings_ms": timings,
        "model": state.settings.openai_generation_model,
        "prompt_version": VERSION,
        "usage": usage,
    }
