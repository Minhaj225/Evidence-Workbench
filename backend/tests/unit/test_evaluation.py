import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from google.genai import types
from pydantic import SecretStr

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


@pytest.mark.parametrize(
    "configured,quota_exhausted,resume",
    [(False, False, False), (True, False, False), (True, True, False), (True, True, True)],
)
async def test_evaluator_terminal_results_and_concurrency(
    settings, store, embedder, configured, quota_exhausted, resume
):
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
        if quota_exhausted:
            generator.answer.side_effect = AppError(
                "generation_quota_exhausted", "Gemini daily quota exhausted.", 429
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
        if resume:
            directory = settings.artifact_root / run["id"]
            directory.mkdir(parents=True)
            row = {
                **records[0].model_dump(),
                "strategy": "baseline",
                "metrics": {
                    "hit_rate_at_5": 0,
                    "precision_at_5": 0,
                    "recall_at_5": 0,
                    "mrr_at_5": 0,
                },
                "timings_ms": {},
                "error_code": "generation_quota_exhausted",
                "error_message": "Gemini daily quota exhausted.",
            }
            (directory / "cases.jsonl").write_text(json.dumps(row) + "\n")
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
    elif quota_exhausted:
        assert report["errors"] == {"generation_quota_exhausted": 65}
        assert generator.answer.await_count == (0 if resume else 1)
        assert all("hit_rate_at_5" in json.loads(row)["metrics"] for row in cases[:60])
        first = json.loads(cases[0])
        assert json.loads(cases[-1])["error_stage"] == "generation"
        assert "quota" in first["error_message"]
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
        models=SimpleNamespace(
            generate_content=AsyncMock(
                return_value=types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            finish_reason="STOP",
                            content=types.Content(
                                parts=[
                                    types.Part(
                                        text=json.dumps(
                                            {
                                                "factual_sentences": 2,
                                                "cited_factual_sentences": 1,
                                                "abstention_supported": True,
                                            }
                                        )
                                    )
                                ]
                            ),
                        )
                    ]
                ),
            )
        )
    )
    assert (await Judge(settings, client).score(case, answer, []))["citation_coverage"] == 0.5
    assert client.models.generate_content.call_args.kwargs["model"] == "gemini-3.5-flash-lite"


async def test_ragas_uses_gemini(settings):
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall

    settings = settings.model_copy(update={"gemini_api_key": SecretStr("test")})
    case = Case.model_validate_json((ROOT / "evaluation/dataset.jsonl").read_text().splitlines()[0])
    answer = GeneratedAnswer(
        answer="Supported [S1].", used_source_ids=["S1"], insufficient_context=False
    )
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=AsyncMock(
                return_value=types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            finish_reason="STOP",
                            content=types.Content(
                                parts=[
                                    types.Part(
                                        text=json.dumps(
                                            {
                                                "factual_sentences": 1,
                                                "cited_factual_sentences": 1,
                                                "abstention_supported": False,
                                            }
                                        )
                                    )
                                ]
                            ),
                        )
                    ]
                ),
            )
        )
    )
    judge = Judge(settings, client)
    with (
        patch.object(Faithfulness, "single_turn_ascore", AsyncMock(return_value=0.75)),
        patch.object(
            LLMContextPrecisionWithReference, "single_turn_ascore", AsyncMock(return_value=1)
        ),
        patch.object(LLMContextRecall, "single_turn_ascore", AsyncMock(return_value=0.5)),
    ):
        scores = await judge.score(case, answer, [])
    assert scores == {
        "faithfulness": 0.75,
        "context_precision": 1.0,
        "context_recall": 0.5,
        "citation_coverage": 1.0,
        "abstention_supported": False,
    }
    assert isinstance(judge.metrics[0].llm.langchain_llm, ChatGoogleGenerativeAI)


@pytest.mark.parametrize(
    "payload",
    [
        '{"factual_sentences": 1, "cited_factual_sentences": 2, "abstention_supported": true}',
        '{"factual_sentences": -1, "cited_factual_sentences": 0, "abstention_supported": true}',
        "{}",
        "bad json",
    ],
)
async def test_invalid_gemini_judgment(settings, payload):
    case = Case.model_validate_json(
        (ROOT / "evaluation/dataset.jsonl").read_text().splitlines()[-1]
    )
    client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=AsyncMock(
                return_value=types.GenerateContentResponse(
                    candidates=[
                        types.Candidate(
                            finish_reason="STOP",
                            content=types.Content(parts=[types.Part(text=payload)]),
                        )
                    ]
                ),
            )
        )
    )
    answer = GeneratedAnswer(
        answer="Insufficient evidence.", used_source_ids=[], insufficient_context=True
    )
    with pytest.raises(AppError, match="evaluation_judge_invalid"):
        await Judge(settings, client).score(case, answer, [])


def test_wrapped_judge_provider_error_is_safe():
    from google.genai import errors

    from backend.app.generation.client import provider_error

    cause = errors.APIError(429, {"error": {"message": "secret"}})
    try:
        raise ValueError("wrapped secret") from cause
    except ValueError as error:
        translated = provider_error(error, fallback="evaluation_judge_failed")
    assert translated.code == "generation_rate_limited"
    assert "secret" not in translated.message


def test_reports_count_missing_scores_without_averaging_them_away():
    rows = [
        {"id": "q-1", "strategy": "enhanced", "answerable": True, "metrics": {"faithfulness": 0.8}},
        {
            "id": "q-2",
            "strategy": "enhanced",
            "answerable": True,
            "metrics": {},
            "error_code": "generation_rate_limited",
        },
    ]
    report = aggregate(rows)
    enhanced = report["strategies"]["enhanced"]
    assert enhanced["metrics"]["faithfulness"] is None
    assert enhanced["metric_counts"]["faithfulness"] == 1
    assert enhanced["cases"] == 2


async def test_ragas_requests_including_output_repairs_are_paced(settings):
    from time import monotonic

    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.exceptions import RagasOutputParserException

    settings = settings.model_copy(
        update={
            "gemini_api_key": SecretStr("test"),
            "gemini_requests_per_minute": 600,
        }
    )
    case = Case.model_validate_json((ROOT / "evaluation/dataset.jsonl").read_text().splitlines()[0])
    answer = GeneratedAnswer(
        answer="Supported [S1].", used_source_ids=["S1"], insufficient_context=False
    )
    times = []

    async def malformed(*args, **kwargs):
        times.append(monotonic())
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="bad JSON"))])

    judge = Judge(settings, SimpleNamespace())
    with patch.object(ChatGoogleGenerativeAI, "_agenerate", malformed):
        with pytest.raises(RagasOutputParserException):
            await judge.score(case, answer, [])
    assert len(times) >= 2
    assert all(b - a >= 0.09 for a, b in zip(times, times[1:], strict=False))
