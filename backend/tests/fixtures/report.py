"""Synthetic UI data, isolated to APP_ENV=test; never benchmark evidence."""

import json
from datetime import UTC, datetime

from backend.app.db import create_database
from backend.app.evaluation.reports import METRICS, aggregate, write_report
from backend.app.models import EvaluationRun

RUN_ID = "00000000-0000-4000-8000-000000000001"


def seed_report(settings):
    directory = settings.artifact_root / RUN_ID
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for strategy in ("baseline", "enhanced"):
        for index in range(30):
            hit = float(strategy == "enhanced" or index >= 2)
            records.append(
                dict(
                    id=f"fixture-{index}",
                    strategy=strategy,
                    answerable=True,
                    question=f"Fixture question {index + 1}",
                    reference_answer="Fixture reference.",
                    answer="Fixture response.",
                    corpus_group="100",
                    difficulty="easy",
                    question_type="definition",
                    evidence=[],
                    retrieved=[],
                    error_code=None,
                    metrics={
                        k: hit if k in ("hit_rate_at_5", "mrr_at_5") else 1.0 for k in METRICS
                    },
                    timings_ms={"total": 10},
                )
            )
    records.extend(
        dict(
            id=f"fixture-u-{i}",
            strategy="enhanced",
            answerable=False,
            question="Fixture unsupported question",
            reference_answer="Insufficient evidence.",
            corpus_group="unanswerable",
            difficulty="hard",
            question_type="unanswerable",
            evidence=[],
            retrieved=[],
            error_code=None,
            metrics={},
            timings_ms={"total": 10},
            insufficient_context=True,
            abstention_supported=True,
        )
        for i in range(5)
    )
    if not (directory / "run.json").exists():
        (directory / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
        write_report(
            directory,
            {
                **aggregate(records),
                "id": RUN_ID,
                "created_at": datetime.now(UTC).isoformat(),
                "dataset_sha256": "synthetic-browser-fixture",
                "configuration": {"fixture": True},
            },
            records,
        )
    sessions = create_database(settings.database_url)
    with sessions() as session:
        if not session.get(EvaluationRun, RUN_ID):
            session.add(
                EvaluationRun(
                    id=RUN_ID,
                    status="completed",
                    dataset_sha256="fixture",
                    corpus_manifest_sha256="fixture",
                    git_commit="fixture",
                    configuration_json='{"fixture":true}',
                    artifact_directory=RUN_ID,
                )
            )
            session.commit()
    sessions.kw["bind"].dispose()
