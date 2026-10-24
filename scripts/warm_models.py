from backend.app.config import Settings
from backend.app.retrieval.embeddings import Embeddings
from backend.app.retrieval.reranker import Reranker


def main() -> None:
    settings = Settings()
    embeddings = Embeddings(settings.embedding_model)
    embeddings.embed_query("What does this document explain?")
    Reranker(settings.reranker_model).score(
        "What does this document explain?", ["It explains risk."]
    )
    print("Embedding and reranking models loaded; CPU inference succeeded.")


if __name__ == "__main__":
    main()
