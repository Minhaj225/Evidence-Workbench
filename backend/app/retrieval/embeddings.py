import threading
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.app.chunking.types import count_tokens, token_slices

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embeddings:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
        module = getattr(self.model, "_first_module", lambda: None)()
        config = getattr(getattr(module, "auto_model", None), "config", None)
        self.revision = getattr(config, "_commit_hash", None)
        self.tokenizer: Any = self.model.tokenizer
        self.lock = threading.Lock()
        # BGE supports 512 model positions, including CLS and SEP.
        # Chunk provenance uses 512 content tokens; extend positions only by splitting at encoding.

    def embed_documents(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("Embedding input must not be empty")
        import torch

        # Avoid silently truncating the last content tokens of a 512-token chunk.
        maximum = self.model.max_seq_length - self.tokenizer.num_special_tokens_to_add(False)
        segments, owners, weights = [], [], []
        for index, text in enumerate(texts):
            for segment, _, _ in token_slices(self.tokenizer, text, maximum):
                segments.append(segment)
                owners.append(index)
                weights.append(count_tokens(self.tokenizer, segment))
        with self.lock, torch.inference_mode():
            vectors = self.model.encode(
                segments,
                batch_size=32,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        result = np.zeros((len(texts), 384), dtype=np.float32)
        for owner, vector, weight in zip(owners, vectors, weights, strict=True):
            result[owner] += vector * weight
        norms = np.linalg.norm(result, axis=1, keepdims=True)
        if np.any(norms == 0) or not np.isfinite(result).all():
            raise ValueError("Model returned invalid embeddings")
        return result / norms

    def embed_query(self, question: str) -> NDArray[np.float32]:
        if not question.strip():
            raise ValueError("Question must not be empty")
        return self.embed_documents([QUERY_PREFIX + question])[0]
