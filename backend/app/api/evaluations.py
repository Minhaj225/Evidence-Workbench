import asyncio
import json
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.app.errors import AppError
from backend.app.models import EvaluationRun

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def public_run(request: Request, run: EvaluationRun) -> dict:
    directory = request.app.state.settings.artifact_root / run.id
    cases = directory / "cases.jsonl"
    progress = len(cases.read_text().splitlines()) if cases.exists() else 0
    return {
        "id": run.id,
        "status": run.status,
        "created_at": run.created_at.replace(tzinfo=UTC),
        "progress_current": progress,
        "progress_total": 65,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "configuration": json.loads(run.configuration_json),
        "report_available": (directory / "run.json").exists(),
    }


@router.get("")
def list_runs(request: Request) -> list[dict]:
    with request.app.state.sessions() as session:
        return [
            public_run(request, run)
            for run in session.scalars(
                select(EvaluationRun).order_by(EvaluationRun.created_at.desc())
            )
        ]


@router.post("", status_code=202)
async def start_evaluation(request: Request) -> dict:
    return await request.app.state.evaluations.enqueue()


@router.get("/{run_id}")
def get_run(run_id: UUID, request: Request) -> dict:
    with request.app.state.sessions() as session:
        run = session.get(EvaluationRun, str(run_id))
        if not run:
            raise AppError("evaluation_not_found", "Evaluation run not found.", 404)
        return public_run(request, run)


@router.get("/{run_id}/report")
async def get_report(run_id: UUID, request: Request, format: str = "json") -> FileResponse:
    formats = {
        "json": ("run.json", "application/json"),
        "csv": ("summary.csv", "text/csv"),
        "markdown": ("report.md", "text/markdown"),
        "cases": ("cases.jsonl", "application/x-ndjson"),
    }
    if format not in formats:
        raise AppError("invalid_report_format", "Choose json, csv, markdown, or cases.")
    name, media_type = formats[format]
    path = request.app.state.settings.artifact_root / str(run_id) / name
    if not await asyncio.to_thread(path.is_file):
        raise AppError("report_not_available", "The report is not available yet.", 404)
    return FileResponse(path, media_type=media_type, filename=f"{run_id}-{name}")
