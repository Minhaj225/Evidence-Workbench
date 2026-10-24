import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class SourceBlock:
    document_id: str
    page_number: int
    block_index: int
    text: str
    bbox: tuple[float, float, float, float] | None = None
    page_width: float | None = None
    page_height: float | None = None
    source_start: int = 0
    source_end: int = 0
    kind: str = "body"


class SourceSpan(BaseModel):
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document_id: str
    document_sha256: str
    strategy: Literal["baseline", "semantic"]
    strategy_version: str
    text: str
    body_text: str
    heading_path: list[str]
    page_start: int
    page_end: int
    source_spans: list[SourceSpan]
    token_count: int = Field(ge=1, le=512)
    content_sha256: str


@dataclass
class Sentence:
    text: str
    span: SourceSpan
    heading_path: list[str] = field(default_factory=list)


def count_tokens(tokenizer: Any, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def token_slices(tokenizer: Any, text: str, maximum: int) -> list[tuple[str, int, int]]:
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)[
        "offset_mapping"
    ]
    result = []
    index = 0
    while index < len(offsets):
        stop = min(index + maximum, len(offsets))
        start, end = offsets[index][0], offsets[stop - 1][1]
        # WordPiece fragments can expand when retokenized at a new boundary.
        while count_tokens(tokenizer, text[start:end]) > maximum:
            stop -= 1
            if stop <= index:
                raise ValueError("A source token exceeds the segment limit")
            end = offsets[stop - 1][1]
        result.append((text[start:end], start, end))
        index = stop
    return result


def make_chunk(
    document_id: str,
    digest: str,
    strategy: Literal["baseline", "semantic"],
    version: str,
    body: str,
    spans: list[SourceSpan],
    headings: list[str],
    tokenizer: Any,
) -> Chunk:
    text = body
    heading = " / ".join(headings)
    if strategy == "semantic" and heading and heading not in body:
        candidate = heading + "\n\n" + body
        if count_tokens(tokenizer, candidate) <= 512:
            text = candidate
    content_digest = hashlib.sha256(text.encode()).hexdigest()
    identity = f"{digest}|{version}|{spans[0].start}|{spans[-1].end}|{content_digest}"
    return Chunk(
        id=str(uuid5(NAMESPACE_URL, identity)),
        document_id=document_id,
        document_sha256=digest,
        strategy=strategy,
        strategy_version=version,
        text=text,
        body_text=body,
        heading_path=headings,
        page_start=spans[0].page,
        page_end=spans[-1].page,
        source_spans=spans,
        token_count=count_tokens(tokenizer, text),
        content_sha256=content_digest,
    )
