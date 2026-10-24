from typing import Any

from backend.app.chunking.types import Chunk, SourceBlock, SourceSpan, count_tokens, make_chunk
from backend.app.errors import AppError

VERSION = "fixed-512-overlap50-source-v4"


def chunk(blocks: list[SourceBlock], digest: str, tokenizer: Any) -> list[Chunk]:
    selected = [b for b in blocks if b.kind in {"body", "heading"} and b.text]
    if not selected:
        raise AppError("empty_document", "There is no text to index.")
    text = "\n\n".join(b.text for b in selected)
    ranges, cursor = [], 0
    for block in selected:
        ranges.append((cursor, cursor + len(block.text), block))
        cursor += len(block.text) + 2
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
    chunks = []
    index = 0
    while index < len(ids):
        stop = min(index + 512, len(ids))
        while True:
            # Preserve punctuation for evidence matching; decoding WordPieces changes spacing.
            body = text[offsets[index][0] : offsets[stop - 1][1]]
            if count_tokens(tokenizer, body) <= 512:
                break
            stop -= 1
        window = offsets[index:stop]
        start, end = window[0][0], window[-1][1]
        spans = [
            SourceSpan(
                page=b.page_number,
                start=b.source_start + max(start - left, 0),
                end=b.source_start + min(end - left, right - left),
            )
            for left, right, b in ranges
            if left < end and right > start
        ]
        if any(c.isalnum() for c in body):
            chunks.append(
                make_chunk(
                    selected[0].document_id, digest, "baseline", VERSION, body, spans, [], tokenizer
                )
            )
        if stop >= len(ids):
            break
        index = max(index + 1, stop - 50)
    if not chunks:
        raise AppError("empty_document", "There is no text to index.")
    return chunks
