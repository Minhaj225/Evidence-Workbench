import os
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient, models

from backend.app.chunking.baseline import chunk
from backend.app.chunking.types import SourceBlock
from backend.app.ingestion.cleaner import clean_blocks
from backend.app.retrieval.service import retrieve
from backend.app.retrieval.vector_store import VectorStore
from backend.tests.fixtures.adapters import FakeReranker

pytestmark = pytest.mark.integration


@pytest.fixture
def real_store(settings):
    url = os.environ.get("TEST_QDRANT_URL")
    if not url:
        pytest.skip("Set TEST_QDRANT_URL to a disposable real Qdrant instance")
    suffix = uuid4().hex
    settings.baseline_collection = f"test_baseline_{suffix}"
    settings.semantic_collection = f"test_semantic_{suffix}"
    store = VectorStore(settings, QdrantClient(url=url, timeout=15))
    try:
        store.ensure_collections()
        yield store
    finally:
        for name in store.collections.values():
            if store.client.collection_exists(name):
                store.client.delete_collection(name)
        store.client.close()


async def test_real_index_filter_idempotency_delete(real_store, embedder):
    ids = [str(uuid4()), str(uuid4())]
    for doc_id, word in zip(ids, ["govern", "manage"], strict=True):
        blocks = clean_blocks([SourceBlock(doc_id, 1, 0, f"{word} policies and controls.")], 1)
        chunks = chunk(blocks, doc_id.replace("-", "") * 2, embedder.tokenizer)
        for strategy in ("baseline", "semantic"):
            real_store.index(
                strategy, chunks, embedder.embed_documents([c.text for c in chunks]), "fixture"
            )
            real_store.index(
                strategy, chunks, embedder.embed_documents([c.text for c in chunks]), "fixture"
            )
            assert real_store.count(strategy, doc_id) == 1
    results, _ = await retrieve(
        "govern policies", [ids[0]], "baseline", embedder, FakeReranker(), real_store
    )
    assert len(results) == 1 and str(results[0].citation.document_id) == ids[0]
    enhanced, _ = await retrieve(
        "govern policies", [ids[0]], "enhanced", embedder, FakeReranker(), real_store
    )
    assert len(enhanced) == 1
    stats = real_store.chunk_statistics(ids)
    assert stats["baseline"]["count"] == 2
    assert 1 <= stats["baseline"]["min"] <= stats["baseline"]["max"] <= 512
    real_store.delete(ids[0])
    assert real_store.count("baseline", ids[0]) == real_store.count("semantic", ids[0]) == 0
    assert real_store.count("baseline", ids[1]) == 1
    for name in real_store.collections.values():
        info = real_store.client.get_collection(name)
        assert info.config.params.vectors.size == 384
        assert info.config.params.vectors.distance == models.Distance.COSINE
        assert {"document_id", "document_sha256", "strategy_version"} <= info.payload_schema.keys()
