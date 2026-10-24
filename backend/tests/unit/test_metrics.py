import pytest
from hypothesis import given
from hypothesis import strategies as st

from backend.app.evaluation.metrics import paired_bootstrap, relevant, retrieval_metrics

GOLD = [
    {"document_sha256": "a", "page": 2, "text": "GOVERN sets policies"},
    {"document_sha256": "a", "page": 3, "text": "MAP describes context"},
]


def chunk(text="GOVERN sets policies", page=2, digest="a"):
    return {"document_sha256": digest, "page_start": page, "page_end": page, "body_text": text}


def test_metric_formulas_and_deduplication():
    result = retrieval_metrics([chunk("wrong"), chunk(), chunk()], GOLD)
    assert result == {
        "hit_rate_at_5": 1.0,
        "precision_at_5": 2 / 3,
        "recall_at_5": 0.5,
        "mrr_at_5": 0.5,
    }
    assert set(retrieval_metrics([], GOLD).values()) == {0.0}
    assert not relevant(chunk(digest="b"), GOLD[0])
    assert not relevant(chunk(page=1), GOLD[0])
    assert relevant(chunk("GOVERN sets"), GOLD[0])
    assert not relevant(chunk(""), GOLD[0])
    with pytest.raises(ValueError):
        retrieval_metrics([], [])


@given(st.lists(st.booleans(), max_size=10))
def test_metrics_bounded(hits):
    results = retrieval_metrics([chunk() if hit else chunk("irrelevant") for hit in hits], GOLD)
    assert all(0 <= value <= 1 for value in results.values())


def test_bootstrap():
    assert paired_bootstrap([0, 0], [1, 1]) == (1.0, 1.0)
    assert paired_bootstrap([0, 1, 0], [1, 1, 1]) == paired_bootstrap([0, 1, 0], [1, 1, 1])
    with pytest.raises(ValueError):
        paired_bootstrap([], [])
