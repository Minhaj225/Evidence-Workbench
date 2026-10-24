import csv
import io
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.evaluation.metrics import paired_bootstrap

METRICS = [
    "hit_rate_at_5",
    "precision_at_5",
    "recall_at_5",
    "mrr_at_5",
    "faithfulness",
    "context_precision",
    "context_recall",
    "citation_validity",
    "citation_coverage",
]


def aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    strategies: dict[str, Any] = {}
    for strategy in ("baseline", "enhanced"):
        rows = [r for r in cases if r["strategy"] == strategy and r["answerable"]]
        values = {}
        for metric in METRICS:
            measured = [r.get("metrics", {}).get(metric) for r in rows]
            # Missing judged scores remain unavailable; never average away failed cases.
            values[metric] = (
                float(np.mean(measured))
                if measured and all(v is not None for v in measured)
                else None
            )
        latencies = {}
        for stage in ("embedding", "dense_retrieval", "reranking", "generation", "total"):
            times = [r["timings_ms"][stage] for r in rows if stage in r.get("timings_ms", {})]
            latencies[stage] = {
                "p50": float(np.percentile(times, 50)) if times else None,
                "p95": float(np.percentile(times, 95)) if times else None,
            }
        strategies[strategy] = {
            "metrics": values,
            "metric_counts": {
                metric: sum(r.get("metrics", {}).get(metric) is not None for r in rows)
                for metric in METRICS
            },
            "latencies_ms": latencies,
            "cases": len(rows),
        }
    deltas, intervals = {}, {}
    for metric in METRICS:
        a, b = [strategies[s]["metrics"][metric] for s in ("baseline", "enhanced")]
        deltas[metric] = None if a is None or b is None else b - a
        if a is not None and b is not None:
            pairs = [
                [r["metrics"][metric] for r in cases if r["strategy"] == s and r["answerable"]]
                for s in ("baseline", "enhanced")
            ]
            intervals[metric] = list(paired_bootstrap(pairs[0], pairs[1]))
    unanswerable = [r for r in cases if not r["answerable"]]
    abstained = sum(
        r.get("insufficient_context", False) and r.get("abstention_supported", False)
        for r in unanswerable
    )
    baseline, enhanced = [strategies[s]["metrics"] for s in ("baseline", "enhanced")]
    gates = {
        "all_cases_terminal": len(cases) == 65,
        "no_case_errors": not any(r.get("error_code") for r in cases),
        "citation_validity": all(
            strategies[s]["metrics"]["citation_validity"] == 1.0 for s in strategies
        ),
        "abstention": abstained >= 4 and len(unanswerable) == 5,
        "hit_rate_gain": deltas["hit_rate_at_5"] is not None
        and deltas["hit_rate_at_5"] >= 2 / 30 - 1e-12,
        "mrr_no_regression": (
            enhanced["mrr_at_5"] is not None
            and baseline["mrr_at_5"] is not None
            and enhanced["mrr_at_5"] >= baseline["mrr_at_5"]
        ),
        "faithfulness": enhanced["faithfulness"] is not None and enhanced["faithfulness"] >= 0.85,
    }
    return {
        "strategies": strategies,
        "deltas": deltas,
        "confidence_intervals": intervals,
        "abstention": {"correct": abstained, "total": len(unanswerable), "rate": abstained / 5},
        "errors": dict(Counter(r["error_code"] for r in cases if r.get("error_code"))),
        "quality_gates": gates,
        "passed": all(gates.values()),
        "usage": {
            key: sum(r.get("usage", {}).get(key, 0) for r in cases)
            for key in ("input_tokens", "output_tokens")
        },
    }


def summary_csv(report: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["metric", "baseline", "enhanced", "delta"])
    for metric in METRICS:
        writer.writerow(
            [
                metric,
                report["strategies"]["baseline"]["metrics"][metric],
                report["strategies"]["enhanced"]["metrics"][metric],
                report["deltas"][metric],
            ]
        )
    return stream.getvalue()


def markdown(report: dict[str, Any], cases: list[dict[str, Any]]) -> str:
    lines = [
        f"# Benchmark {report['id']}",
        "",
        f"Timestamp: {report['created_at']}",
        f"Dataset SHA-256: `{report['dataset_sha256']}`",
        "",
        f"Quality gates: {'PASS' if report['passed'] else 'FAIL'}. Missing scores are unavailable.",
        "",
        "| Metric | Baseline | Enhanced | Delta |",
        "|---|---:|---:|---:|",
    ]

    def display(value: Any) -> str:
        return "unavailable" if value is None else f"{value:.6f}"

    for metric in METRICS:
        a, b = [report["strategies"][s]["metrics"][metric] for s in ("baseline", "enhanced")]
        lines.append(
            f"| {metric} | {display(a)} | {display(b)} | {display(report['deltas'][metric])} |"
        )
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            "```json",
            json.dumps(report["configuration"], indent=2),
            "```",
            "",
            "## Paired bootstrap 95% intervals",
            "",
            json.dumps(report["confidence_intervals"], indent=2),
            "",
            "## Latencies (ms)",
            "",
        ]
    )
    for strategy in ("baseline", "enhanced"):
        lines.extend(
            [
                strategy,
                "```json",
                json.dumps(report["strategies"][strategy]["latencies_ms"], indent=2),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "## Abstention and errors",
            "",
            json.dumps(report["abstention"]),
            json.dumps(report["errors"]),
            "",
            "## Representative cases",
            "",
        ]
    )
    wins = [
        r
        for r in cases
        if r["strategy"] == "enhanced" and r.get("metrics", {}).get("hit_rate_at_5") == 1
    ]
    failures = [
        r for r in cases if r.get("error_code") or r.get("metrics", {}).get("hit_rate_at_5") == 0
    ]
    for label, rows in (("Retrieval successes", wins), ("Failures", failures)):
        lines.append(f"### {label}")
        if not rows:
            lines.append("No cases in this category were observed.")
        for row in rows[:3]:
            lines.append(
                f"- {row['id']} ({row['strategy']}): {row.get('error_code') or row['metrics']}"
            )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "Born-digital PDFs only; no OCR or structural table understanding. "
            "English-focused local models. "
            "This small curated corpus cannot establish general retrieval superiority. "
            "LLM judgments are "
            "subjective and require a configured provider. Latency reflects one CPU host. "
            "Citation IDs "
            "prove source membership, not factual entailment. Failed runs are retained.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(directory: Path, report: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    # Refuse to replace a finalized run, including a failed quality-gate run.
    if (directory / "run.json").exists():
        raise FileExistsError("Run is already finalized")
    (directory / "summary.csv").write_text(summary_csv(report))
    (directory / "report.md").write_text(markdown(report, cases))
    (directory / "run.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    saved = json.loads((directory / "run.json").read_text())
    if (directory / "summary.csv").read_text() != summary_csv(saved):
        raise ValueError("Report cross-validation failed")
    temporary = directory.parent / ".latest.tmp"
    temporary.write_text(directory.name + "\n")
    os.replace(temporary, directory.parent / "latest")
