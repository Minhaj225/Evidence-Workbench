import threading


class Reranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, device="cpu")
        config = getattr(getattr(self.model, "model", None), "config", None)
        self.revision = getattr(config, "_commit_hash", None)
        self.lock = threading.Lock()

    def score(self, question: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        import torch

        with self.lock, torch.inference_mode():
            scores = self.model.predict(
                [(question, text) for text in passages], batch_size=32, show_progress_bar=False
            )
        return [float(score) for score in scores]
