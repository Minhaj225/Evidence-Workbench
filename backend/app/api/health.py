import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    state = request.app.state
    components = {
        "database": "healthy",
        "qdrant": "healthy",
        "embedding_model": "healthy" if state.embedder else "unavailable",
        "reranker": "healthy" if state.reranker else "unavailable",
        "worker": "healthy"
        if state.worker
        and state.worker.task
        and not state.worker.task.done()
        and state.documents.accepting
        else "unavailable",
        "generation": "healthy" if state.generator.client is not None else "degraded",
    }
    try:
        with state.sessions() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        components["database"] = "unavailable"
    try:
        await asyncio.to_thread(state.store.ping)
    except Exception:
        components["qdrant"] = "unavailable"
    status = (
        "unavailable"
        if components["database"] == "unavailable"
        else "degraded"
        if any(v != "healthy" for v in components.values())
        else "healthy"
    )
    return JSONResponse(
        {"status": status, "components": components},
        status_code=503 if status == "unavailable" else 200,
    )
