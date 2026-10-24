import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=2000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    strategy: Literal["baseline", "enhanced"] = "enhanced"

    @field_validator("question")
    @classmethod
    def question_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or not any(c.isalnum() for c in value):
            raise ValueError("Enter a question containing letters or numbers")
        return value


SourceID = Annotated[str, Field(pattern=r"^S[1-5]$")]


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1)
    used_source_ids: list[SourceID]
    insufficient_context: bool

    @field_validator("answer")
    @classmethod
    def nonempty_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Answer must contain text")
        return value

    @field_validator("used_source_ids")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Source IDs must be unique")
        return value


class Citation(BaseModel):
    source_id: SourceID
    chunk_id: UUID
    document_id: UUID
    document_title: str
    heading_path: list[str]
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    excerpt: str
    dense_score: float = Field(allow_inf_nan=False)
    reranker_score: float | None = Field(default=None, allow_inf_nan=False)


def excerpt(text: str) -> str:
    if len(text) <= 1200:
        return text
    prefix = text[:1200]
    match = re.search(r"\s+\S*$", prefix)
    return prefix[: match.start()] if match else prefix
