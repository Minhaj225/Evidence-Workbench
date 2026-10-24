from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(8000, ge=1, le=65535)
    database_url: str = "sqlite:///./data/app.db"
    document_root: Path = Path("data/documents")
    page_cache_root: Path = Path("data/pages")
    artifact_root: Path = Path("artifacts/evaluations")
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    baseline_collection: str = "rag_baseline_v1"
    semantic_collection: str = "rag_semantic_v1"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_generation_model: str = "gemini-3.5-flash-lite"
    gemini_evaluator_model: str = "gemini-3.5-flash-lite"
    max_upload_bytes: int = Field(20971520, gt=0)
    max_pdf_pages: int = Field(300, gt=0)
    max_question_chars: int = Field(2000, ge=3, le=2000)
    max_selected_documents: int = Field(20, ge=1, le=20)
    generation_timeout_seconds: float = Field(60, gt=0)
    generation_concurrency: int = Field(1, ge=1)
    cors_origins: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_url")
    @classmethod
    def allow_any_url(cls, value: str) -> str:
        """Allow any valid SQLAlchemy URL; SQLite local overrides via env var."""
        # Support postgres://, mysql://, mssql://, sqlite:// etc.
        return value

    @field_validator("cors_origins")
    @classmethod
    def exact_origins(cls, value: str) -> str:
        from urllib.parse import urlsplit

        for origin in value.split(","):
            url = urlsplit(origin.strip())
            if url.scheme not in {"http", "https"} or not url.netloc or url.path:
                raise ValueError("CORS requires exact HTTP origins without paths")
            if "*" in origin or url.username or url.query or url.fragment:
                raise ValueError("CORS requires exact origins")
        return value

    @model_validator(mode="after")
    def distinct_collections(self) -> "Settings":
        if self.baseline_collection == self.semantic_collection:
            raise ValueError("Strategy collections must be different")
        return self
