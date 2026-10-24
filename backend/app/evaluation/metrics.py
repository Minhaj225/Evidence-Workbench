import re
from typing import Any

import numpy as np

from backend.app.ingestion.cleaner import match_normalize


def relevant(chunk: dict[str, Any], evidence: dict[str, Any]) -> bool:
    if chunk["document_sha256"] != evidence["document_sha256"]:
        return False
    if not chunk["page_start"] <= evidence["page"] <= chunk["page_end"]:
        return False
    body, gold = match_normalize(chunk["body_text"]), match_normalize(evidence["text"])
    if not body or not gold:
        return False
    if gold in body:
        return True
    if body in gold:
        short = set(re.findall(r"\w+", body))
        long = set(re.findall(r"\w+", gold))
        return bool(short) and len(short & long) / len(short) >= 0.8
    return False


def retrieval_metrics(
    chunks: list[dict[str, Any]], evidence: list[dict[str, Any]]
) -> dict[str, float]:
    if not evidence:
        raise ValueError("Retrieval metrics require answerable evidence")
    matches = [[relevant(chunk, gold) for gold in evidence] for chunk in chunks[:5]]
    hits = [any(row) for row in matches]
    covered = sum(any(row[i] for row in matches) for i in range(len(evidence)))
    return {
        "hit_rate_at_5": float(any(hits)),
        "precision_at_5": sum(hits) / len(hits) if hits else 0.0,
        "recall_at_5": covered / len(evidence),
        "mrr_at_5": next((1.0 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0),
    }


def paired_bootstrap(
    baseline: list[float], enhanced: list[float], seed: int = 42, samples: int = 10000
) -> tuple[float, float]:
    if len(baseline) != len(enhanced) or not baseline or samples < 1:
        raise ValueError(
            "Bootstrap requires equal nonempty paired observations and positive samples"
        )
    delta = np.asarray(enhanced, dtype=float) - np.asarray(baseline, dtype=float)
    if not np.isfinite(delta).all():
        raise ValueError("Bootstrap inputs must be finite")
    rng = np.random.default_rng(seed)
    means = np.mean(delta[rng.integers(0, len(delta), size=(samples, len(delta)))], axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)
