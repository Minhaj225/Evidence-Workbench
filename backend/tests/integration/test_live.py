import os
from uuid import uuid4

import pytest

from backend.app.chunking.baseline import chunk
from backend.app.chunking.types import SourceBlock
from backend.app.config import Settings
from backend.app.evaluation.dataset import Case
from backend.app.evaluation.runner import Judge
from backend.app.generation.client import Generator
from backend.app.retrieval.service import Retrieved
from backend.app.schemas import Citation
from backend.tests.fixtures.adapters import WordTokenizer


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1", reason="Explicit opt-in required"
)
async def test_live_grounded_schema():
    settings = Settings()
    assert settings.gemini_api_key.get_secret_value(), "Configure GEMINI_API_KEY locally"
    document_id = str(uuid4())
    source = chunk(
        [SourceBlock(document_id, 1, 0, "The launch year was 2020.", source_end=25)],
        "a" * 64,
        WordTokenizer(),
    )[0]
    citation = Citation(
        source_id="S1",
        chunk_id=source.id,
        document_id=document_id,
        document_title="Smoke fixture",
        heading_path=[],
        page_start=1,
        page_end=1,
        excerpt=source.body_text,
        dense_score=1,
        reranker_score=None,
    )
    generator = Generator(settings)
    try:
        answer, usage = await generator.answer(
            "What was the launch year?", [Retrieved(source, citation)]
        )
        assert not answer.insufficient_context and answer.used_source_ids == ["S1"]
        assert usage["output_tokens"] > 0
        case = Case(
            id="smoke",
            answerable=True,
            question="What was the launch year?",
            reference_answer="The launch year was 2020.",
            topic="launch",
            question_type="definition",
            difficulty="easy",
            corpus_group="100",
            evidence=[],
        )
        scores = await Judge(
            settings,
            generator.client,
            rate_limiter=generator.rate_limiter,
        ).score(case, answer, [Retrieved(source, citation)])
        assert scores["faithfulness"] == 1.0
        assert scores["context_precision"] == pytest.approx(1.0)
        assert scores["context_recall"] == 1.0
        assert scores["citation_coverage"] == 1.0
    finally:
        await generator.close()
