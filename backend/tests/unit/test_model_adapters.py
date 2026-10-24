import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from backend.app.retrieval.embeddings import QUERY_PREFIX, Embeddings
from backend.app.retrieval.reranker import Reranker


def test_embedding_normalization_and_no_truncation(tokenizer):
    tokenizer.num_special_tokens_to_add = lambda pair: 2
    seen = []

    def encode(texts, **kwargs):
        seen.extend(texts)
        assert kwargs["normalize_embeddings"] and kwargs["batch_size"] == 32
        return np.ones((len(texts), 384), dtype=np.float32)

    model = SimpleNamespace(tokenizer=tokenizer, max_seq_length=512, encode=encode)
    with patch.dict(
        sys.modules,
        {"sentence_transformers": SimpleNamespace(SentenceTransformer=lambda *a, **k: model)},
    ):
        embeddings = Embeddings("fixture")
    values = embeddings.embed_documents(["word " * 512])
    assert len(seen) == 2 and sum(len(tokenizer.encode(s)) for s in seen) == 512
    assert values.shape == (1, 384) and values.dtype == np.float32
    assert np.linalg.norm(values[0]) == pytest.approx(1.0)
    embeddings.embed_query("supported question")
    assert seen[-1].startswith(QUERY_PREFIX.strip())
    with pytest.raises(ValueError):
        embeddings.embed_query(" ")
    with pytest.raises(ValueError):
        embeddings.embed_documents([])


def test_reranker_adapter():
    model = SimpleNamespace(predict=lambda pairs, **kwargs: np.asarray([1.0, 2.0]))
    with patch.dict(
        sys.modules, {"sentence_transformers": SimpleNamespace(CrossEncoder=lambda *a, **k: model)}
    ):
        reranker = Reranker("fixture")
    assert reranker.score("question", []) == []
    assert reranker.score("question", ["a", "b"]) == [1.0, 2.0]
    assert isinstance(reranker.lock, type(threading.Lock()))
