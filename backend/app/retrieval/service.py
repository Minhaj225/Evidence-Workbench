import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import UUID

from backend.app.chunking.types import Chunk
from backend.app.schemas import Citation, excerpt


@dataclass
class Retrieved:
    chunk: Chunk
    citation: Citation


async def retrieve(
    question: str, document_ids: list[str], strategy: str, embedder: Any, reranker: Any, store: Any
) -> tuple[list[Retrieved], dict[str, float]]:
    start = perf_counter()
    vector = await asyncio.to_thread(embedder.embed_query, question)
    embedded = perf_counter()
    candidates = await asyncio.to_thread(
        store.search,
        "semantic" if strategy == "enhanced" else "baseline",
        vector,
        document_ids,
        50 if strategy == "enhanced" else 5,
    )
    searched = perf_counter()
    parsed = [
        (
            point,
            Chunk.model_validate(
                {
                    "id": str(point.id),
                    **{k: v for k, v in point.payload.items() if k != "original_filename"},
                }
            ),
        )
        for point in candidates
    ]
    if strategy == "enhanced":
        scores = await asyncio.to_thread(reranker.score, question, [c.body_text for _, c in parsed])
        ranked = sorted(
            zip(parsed, scores, strict=True),
            key=lambda item: (-item[1], -item[0][0].score, item[0][1].id),
        )
    else:
        ranked = [
            (pair, None) for pair in sorted(parsed, key=lambda pair: (-pair[0].score, pair[1].id))
        ]
    results = []
    for index, ((point, chunk), score) in enumerate(ranked[:5], 1):
        citation = Citation(
            source_id=f"S{index}",
            chunk_id=UUID(chunk.id),
            document_id=UUID(chunk.document_id),
            document_title=point.payload["original_filename"],
            heading_path=chunk.heading_path,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            excerpt=excerpt(chunk.body_text),
            dense_score=point.score,
            reranker_score=score,
        )
        results.append(Retrieved(chunk, citation))
    return results, {
        "embedding": (embedded - start) * 1000,
        "dense_retrieval": (searched - embedded) * 1000,
        "reranking": (perf_counter() - searched) * 1000 if strategy == "enhanced" else 0,
    }
