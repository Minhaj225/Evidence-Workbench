import hashlib

import numpy as np
import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from backend.app.chunking import baseline, semantic
from backend.app.chunking.types import SourceBlock, count_tokens
from backend.app.errors import AppError
from backend.app.ingestion.cleaner import clean_blocks
from backend.tests.fixtures.adapters import FakeEmbeddings

DIGEST = hashlib.sha256(b"fixture").hexdigest()


def blocks(text, document_id="843d70c1-6bb3-4f82-8a88-0a43204babce"):
    return clean_blocks([SourceBlock(document_id, 1, 0, text)], 1)


def test_baseline_windows(tokenizer):
    text = " ".join(f"word{i}" for i in range(1100))
    chunks = baseline.chunk(blocks(text), DIGEST, tokenizer)
    assert [c.token_count for c in chunks] == [512, 512, 176]
    first, second = [tokenizer.encode(c.text) for c in chunks[:2]]
    assert first[-50:] == second[:50]
    assert chunks[1].source_spans[0].start == text.index("word462")
    assert chunks == baseline.chunk(blocks(text), DIGEST, tokenizer)


def test_baseline_preserves_evidence_punctuation(tokenizer):
    text = "The organization's risk tolerance (see Appendix A) is context-specific."
    result = baseline.chunk(blocks(text), DIGEST, tokenizer)
    assert result[0].body_text == text


def test_thresholds():
    assert semantic.boundary_threshold([]) == float("inf")
    assert semantic.boundary_threshold([0.1, 0.2, 0.3]) == pytest.approx(0.3)
    distances = list(np.linspace(0, 1, 30))
    assert semantic.boundary_threshold(distances) == pytest.approx(0.95)


def test_single_and_oversized(embedder):
    for length in [1, 70, 448, 449, 1025]:
        text = " ".join(f"word{i}" for i in range(length)) + "."
        source = blocks(text)
        chunks = semantic.chunk(source, DIGEST, embedder.tokenizer, embedder)
        assert all(c.token_count <= 512 for c in chunks)
        assert all(f"word{i}" in " ".join(c.body_text for c in chunks) for i in range(length))
        if length == 1:
            assert len(chunks) == 1


def test_hard_heading_boundaries(embedder):
    source = clean_blocks(
        [
            SourceBlock("doc", 1, 0, "First section", kind="heading"),
            SourceBlock("doc", 1, 1, "The first body has a fact."),
            SourceBlock("doc", 2, 0, "Second section", kind="heading"),
            SourceBlock("doc", 2, 1, "Another body has another fact."),
        ],
        2,
    )
    chunks = semantic.chunk(source, DIGEST, embedder.tokenizer, embedder)
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["First section"]
    assert chunks[1].page_start == 2


@given(st.lists(st.integers(min_value=1, max_value=100), min_size=1, max_size=40))
@hypothesis_settings(max_examples=35, deadline=None)
def test_semantic_properties(lengths):
    embedder = FakeEmbeddings()
    sentences = [
        "Topic " + " ".join([f"term{i}"] * length) + "." for i, length in enumerate(lengths)
    ]
    source = blocks(" ".join(sentences))
    result = semantic.chunk(source, DIGEST, embedder.tokenizer, embedder)
    assert result == semantic.chunk(source, DIGEST, embedder.tokenizer, embedder)
    assert all(count_tokens(embedder.tokenizer, c.text) <= 512 for c in result)
    assert all(any(sentence in c.body_text for c in result) for sentence in sentences)
    starts = [c.source_spans[0].start for c in result]
    assert starts == sorted(starts)


def test_empty_input(embedder):
    with pytest.raises(AppError, match="empty_document"):
        baseline.chunk([], DIGEST, embedder.tokenizer)
    with pytest.raises(AppError, match="empty_document"):
        semantic.chunk([], DIGEST, embedder.tokenizer, embedder)


def test_standalone_token_expansion_is_bounded(tokenizer):
    from backend.app.chunking.types import token_slices

    encode = tokenizer.encode

    def expanded(text, **kwargs):
        ids = encode(text, **kwargs)
        return ids + [0] if text.startswith(("word462 ", "word448 ")) else ids

    tokenizer.encode = expanded
    text = " ".join(f"word{i}" for i in range(1100))
    fixed = baseline.chunk(blocks(text), DIGEST, tokenizer)
    assert all(c.token_count <= 512 for c in fixed)
    assert fixed[1].source_spans[0].start == text.index("word462")
    pieces = token_slices(tokenizer, text, 448)
    assert all(count_tokens(tokenizer, s) <= 448 for s, _, _ in pieces)
    assert "".join(s.replace(" ", "") for s, _, _ in pieces) == text.replace(" ", "")
