from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)


class Document(Timestamps, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("status IN ('queued','processing','ready','failed','deleting')"),
        CheckConstraint("byte_size >= 0"),
        CheckConstraint("page_count IS NULL OR page_count > 0"),
        CheckConstraint("baseline_chunk_count IS NULL OR baseline_chunk_count >= 0"),
        CheckConstraint("semantic_chunk_count IS NULL OR semantic_chunk_count >= 0"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    original_filename: Mapped[str] = mapped_column(String(180))
    media_type: Mapped[str]
    byte_size: Mapped[int]
    page_count: Mapped[int | None]
    status: Mapped[str] = mapped_column(default="queued")
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    baseline_chunk_count: Mapped[int | None]
    semantic_chunk_count: Mapped[int | None]
    parser_version: Mapped[str | None]
    baseline_chunker_version: Mapped[str | None]
    semantic_chunker_version: Mapped[str | None]
    embedding_model: Mapped[str | None]
    ready_at: Mapped[datetime | None]


class IngestionJob(Timestamps, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')"),
        CheckConstraint("stage IN ('validate','parse','clean','chunk','embed','index','finalize')"),
        CheckConstraint("attempt >= 1"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    stage: Mapped[str] = mapped_column(default="validate")
    progress_current: Mapped[int | None]
    progress_total: Mapped[int | None]
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class EvaluationRun(Timestamps, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (CheckConstraint("status IN ('queued','running','completed','failed')"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(default="queued")
    dataset_sha256: Mapped[str]
    corpus_manifest_sha256: Mapped[str]
    git_commit: Mapped[str]
    configuration_json: Mapped[str] = mapped_column(Text)
    artifact_directory: Mapped[str]
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
