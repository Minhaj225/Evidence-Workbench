from typing import Any

from qdrant_client import QdrantClient, models

from backend.app.chunking.types import Chunk
from backend.app.config import Settings
from backend.app.errors import AppError


class VectorStore:
    def __init__(self, settings: Settings, client: QdrantClient | None = None):
        self.collections = {
            "baseline": settings.baseline_collection,
            "semantic": settings.semantic_collection,
        }
        self.client = (
            client
            if client is not None
            else QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key.get_secret_value() or None,
                timeout=15,
            )
        )

    def ensure_collections(self) -> None:
        for name in self.collections.values():
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    name,
                    vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
                    shard_number=1,
                    replication_factor=1,
                )
            info = self.client.get_collection(name)
            vectors = info.config.params.vectors
            if (
                not isinstance(vectors, models.VectorParams)
                or vectors.size != 384
                or vectors.distance != models.Distance.COSINE
            ):
                raise AppError(
                    "vector_store_configuration", "Vector collection configuration differs.", 503
                )
            for key in ("document_id", "document_sha256", "strategy_version"):
                self.client.create_payload_index(
                    name, key, models.PayloadSchemaType.KEYWORD, wait=True
                )

    def ping(self) -> None:
        self.client.get_collections()

    def chunk_statistics(self, document_ids: list[str]) -> dict[str, Any]:
        statistics = {}
        for strategy, name in self.collections.items():
            sizes: list[int] = []
            offset = None
            while True:
                points, offset = self.client.scroll(
                    name,
                    scroll_filter=self.document_filter(document_ids),
                    limit=256,
                    offset=offset,
                    with_payload=["token_count"],
                    with_vectors=False,
                )
                sizes.extend(int(p.payload["token_count"]) for p in points if p.payload)
                if offset is None:
                    break
            statistics[strategy] = {
                "count": len(sizes),
                "min": min(sizes) if sizes else None,
                "max": max(sizes) if sizes else None,
                "mean": sum(sizes) / len(sizes) if sizes else None,
            }
        return statistics

    @staticmethod
    def document_filter(document_ids: list[str]) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))]
        )

    def index(self, strategy: str, chunks: list[Chunk], vectors: Any, title: str) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts differ")
        points = [
            models.PointStruct(
                id=chunk.id,
                vector=vector.tolist(),
                payload={**chunk.model_dump(exclude={"id"}), "original_filename": title},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self.client.upload_points(self.collections[strategy], points, batch_size=64, wait=True)

    def count(self, strategy: str, document_id: str) -> int:
        return self.client.count(
            self.collections[strategy], exact=True, count_filter=self.document_filter([document_id])
        ).count

    def delete(self, document_id: str) -> None:
        failures = []
        for name in self.collections.values():
            try:
                self.client.delete(
                    name,
                    points_selector=models.FilterSelector(
                        filter=self.document_filter([document_id])
                    ),
                    wait=True,
                )
            except Exception:
                failures.append(name)
        if failures:
            raise AppError(
                "vector_store_unavailable", "Vector cleanup failed; retry the operation.", 503
            )

    def search(self, strategy: str, vector: Any, documents: list[str], limit: int) -> list[Any]:
        try:
            return self.client.query_points(
                self.collections[strategy],
                query=vector.tolist(),
                query_filter=self.document_filter(documents),
                limit=limit,
                with_payload=True,
            ).points
        except Exception as exc:
            raise AppError(
                "vector_store_unavailable", "Vector search is unavailable.", 503
            ) from exc
