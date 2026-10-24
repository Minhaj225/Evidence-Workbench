import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from backend.app.db import create_database
from backend.app.errors import AppError
from backend.app.evaluation.dataset import Case, load_dataset
from backend.app.evaluation.reports import aggregate, summary_csv, write_report
from backend.app.evaluation.runner import Evaluator, Judge
from backend.app.generation.client import Generator
from backend.app.ingestion.service import DocumentService
from backend.app.models import Document, EvaluationRun
from backend.app.schemas import GeneratedAnswer
from scripts.download_corpus import ROOT


def test_dataset_and_evidence_validation(tmp_path):
    with pytest.raises(AppError, match="evaluation_dataset_invalid"):
        load_dataset(tmp_path)
    records = [
        Case.model_validate_json(line)
        for line in (ROOT / "evaluation/dataset.jsonl").read_text().splitlines()
    ]
    assert len(records) == 35 and sum(c.answerable for c in records) == 30
    assert all(c.answerable == bool(c.evidence) for c in records)


def test_artifact_immutability_and_missing_metrics(tmp_path):
    rows = [
        {
            "id": f"q-{i}",
            "strategy": s,
            "answerable": True,
            "metrics": {
                "hit_rate_at_5": 0.0,
                "precision_at_5": 0.0,
                "recall_at_5": 0.0,
                "mrr_at_5": 0.0,
            },
            "error_code": "generation_not_configured",
            "timings_ms": {"total": 1},
        }
        for s in ("baseline", "enhanced")
        for i in range(30)
    ]
    rows += [
        {
            "id": f"u-{i}",
            "strategy": "enhanced",
            "answerable": False,
            "error_code": "generation_not_configured",
        }
        for i in range(5)
    ]
    report = {
        **aggregate(rows),
        "id": "test",
        "created_at": "2026-10-18",
        "dataset_sha256": "abc",
        "configuration": {},
    }
    assert not report["passed"]
    assert report["strategies"]["enhanced"]["metrics"]["faithfulness"] is None
    assert report["errors"] == {"generation_not_configured": 65}
    directory = tmp_path / "test"
    directory.mkdir()
    write_report(directory, report, rows)
    assert (tmp_path / "latest").read_text().strip() == "test"
    assert (directory / "summary.csv").read_text() == summary_csv(report)
    with pytest.raises(FileExistsError):
        write_report(directory, report, rows)


@pytest.mark.parametrize("configured", [False, True])
async def test_evaluator_terminal_results_and_concurrency(settings, store, embedder, configured):
    from backend.tests.fixtures.adapters import FakeReranker

    sessions = create_database(settings.database_url)
    service = DocumentService(settings, sessions, store)
    service.accepting = True
    generator = Generator(settings)
    if configured:
        generator.client = SimpleNamespace()
        generator.answer = AsyncMock(
            return_value=(
                GeneratedAnswer(
                    answer="Insufficient evidence.", used_source_ids=[], insufficient_context=True
                ),
                {"input_tokens": 1, "output_tokens": 1},
            )
        )
    state = SimpleNamespace(
        settings=settings,
        sessions=sessions,
        documents=service,
        store=store,
        embedder=embedder,
        reranker=FakeReranker(),
        generator=generator,
    )
    evaluator = Evaluator(state)
    records = [
        Case.model_validate_json(line)
        for line in (ROOT / "evaluation/dataset.jsonl").read_text().splitlines()
    ]
    manifest = json.loads((ROOT / "corpus/manifest.json").read_text())
    doc = Document(
        id=str(uuid4()),
        sha256="a" * 64,
        status="ready",
        original_filename="fixture.txt",
        media_type="text/plain",
        byte_size=1,
        baseline_chunk_count=0,
        semantic_chunk_count=0,
    )
    with (
        patch("backend.app.evaluation.runner.subprocess.run", side_effect=FileNotFoundError),
        patch(
            "backend.app.evaluation.runner.load_dataset",
            return_value=(records, manifest, "digest", "manifest"),
        ),
        patch.object(evaluator, "ready_corpus", return_value=[doc]),
        patch(
            "backend.app.evaluation.runner.retrieve",
            AsyncMock(return_value=([], {"embedding": 1, "dense_retrieval": 1, "reranking": 1})),
        ),
        patch.object(
            Judge,
            "score",
            AsyncMock(
                side_effect=lambda *args: {
                    "faithfulness": 1.0,
                    "context_precision": 1.0,
                    "context_recall": 1.0,
                    "citation_coverage": 1.0,
                    "abstention_supported": True,
                }
            ),
        ),
    ):
        run = await evaluator.enqueue()
        with pytest.raises(AppError, match="evaluation_already_running"):
            await evaluator.enqueue()
        await evaluator.run(run["id"])
    with sessions() as session:
        saved = session.get(EvaluationRun, run["id"])
        assert saved.status == "failed"
        assert saved.error_code == "evaluation_quality_gate_failed"
    directory = settings.artifact_root / run["id"]
    cases = (directory / "cases.jsonl").read_text().splitlines()
    assert len(cases) == 65
    report = json.loads((directory / "run.json").read_text())
    assert report["quality_gates"]["all_cases_terminal"]
    if not configured:
        assert report["errors"]["generation_not_configured"] == 65
    else:
        assert report["errors"] == {}
        assert report["abstention"]["correct"] == 5
    sessions.kw["bind"].dispose()


async def test_judge_schema_and_missing_key(settings):
    case = Case.model_validate_json(
        (ROOT / "evaluation/dataset.jsonl").read_text().splitlines()[-1]
    )
    answer = GeneratedAnswer(
        answer="Insufficient evidence.", used_source_ids=[], insufficient_context=True
    )
    with pytest.raises(AppError, match="generation_not_configured"):
        await Judge(settings, None).score(case, answer, [])
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=AsyncMock(
                return_value=SimpleNamespace(
                    output_parsed=SimpleNamespace(
                        factual_sentences=2, cited_factual_sentences=1, abstention_supported=True
                    )
                )
            )
        )
    )
    assert (await Judge(settings, client).score(case, answer, []))["citation_coverage"] == 0.5
