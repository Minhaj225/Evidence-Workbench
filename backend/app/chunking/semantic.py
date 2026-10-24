from typing import Any

import numpy as np
from syntok.segmenter import analyze

from backend.app.chunking.types import (
    Chunk,
    Sentence,
    SourceBlock,
    SourceSpan,
    count_tokens,
    make_chunk,
    token_slices,
)
from backend.app.errors import AppError

VERSION = "semantic-p95-384-128-448-overlap64-v2"


def prepare_sentences(blocks: list[SourceBlock], tokenizer: Any) -> list[Sentence]:
    sentences: list[Sentence] = []
    headings: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            headings = [block.text]
            continue
        if block.kind != "body":
            continue
        for paragraph in analyze(block.text):
            for tokens in paragraph:
                if not tokens:
                    continue
                start = tokens[0].offset
                end = tokens[-1].offset + len(tokens[-1].value)
                for text, left, right in token_slices(tokenizer, block.text[start:end], 448):
                    sentences.append(
                        Sentence(
                            text,
                            SourceSpan(
                                page=block.page_number,
                                start=block.source_start + start + left,
                                end=block.source_start + start + right,
                            ),
                            headings.copy(),
                        )
                    )
    # A heading-only document still has source content worth retrieving.
    if not sentences:
        for block in blocks:
            if block.kind == "heading":
                for text, left, right in token_slices(tokenizer, block.text, 448):
                    sentences.append(
                        Sentence(
                            text,
                            SourceSpan(
                                page=block.page_number,
                                start=block.source_start + left,
                                end=block.source_start + right,
                            ),
                        )
                    )
    return sentences


def boundary_threshold(distances: list[float]) -> float:
    if not distances:
        return float("inf")
    if len(distances) >= 20:
        return float(np.percentile(distances, 95))
    q1, median, q3 = np.percentile(distances, [25, 50, 75])
    return float(min(max(distances), median + 1.5 * (q3 - q1)))


def chunk(blocks: list[SourceBlock], digest: str, tokenizer: Any, embedder: Any) -> list[Chunk]:
    sentences = prepare_sentences(blocks, tokenizer)
    if not sentences:
        raise AppError("empty_document", "There is no text to index.")
    vectors = embedder.embed_documents([s.text for s in sentences])
    distances = [float(1 - np.dot(a, b)) for a, b in zip(vectors[:-1], vectors[1:], strict=True)]
    hard = {
        i
        for i in range(1, len(sentences))
        if sentences[i].heading_path != sentences[i - 1].heading_path
    }
    threshold = boundary_threshold([d for i, d in enumerate(distances, 1) if i not in hard])
    boundaries = {i for i, d in enumerate(distances, 1) if d >= threshold} | hard
    cuts = [0, *sorted(boundaries), len(sentences)]
    groups = [list(range(a, b)) for a, b in zip(cuts[:-1], cuts[1:], strict=True)]

    def size(group: list[int]) -> int:
        return count_tokens(tokenizer, " ".join(sentences[i].text for i in group))

    i = 0
    while i < len(groups):
        if size(groups[i]) < 128:
            choices = []
            for neighbor in (i - 1, i + 1):
                if 0 <= neighbor < len(groups):
                    left, right = sorted((i, neighbor))
                    boundary = groups[right][0]
                    if boundary not in hard and size(groups[left] + groups[right]) <= 448:
                        choices.append((distances[boundary - 1], left, right))
            if choices:
                _, left, right = min(choices)
                groups[left] += groups.pop(right)
                i = max(left - 1, 0)
                continue
        i += 1

    def split(group: list[int]) -> list[list[int]]:
        if size(group) <= 448:
            return [group]
        candidates = [j for j in range(1, len(group)) if group[j] in boundaries]
        if candidates:
            pivot = max(candidates, key=lambda j: (distances[group[j] - 1], -j))
        else:
            fitting = [j for j in range(1, len(group)) if size(group[:j]) <= 448]
            pivot = min(fitting, key=lambda j: abs(384 - size(group[:j])))
        return split(group[:pivot]) + split(group[pivot:])

    groups = [part for group in groups for part in split(group)]
    result = []
    for index, group in enumerate(groups):
        final = group.copy()
        if index and group[0] not in hard:
            previous = groups[index - 1][-1]
            if size([previous]) <= 64 and size([previous, *group]) <= 512:
                final.insert(0, previous)
        body = " ".join(sentences[j].text for j in final)
        result.append(
            make_chunk(
                blocks[0].document_id,
                digest,
                "semantic",
                VERSION,
                body,
                [sentences[j].span for j in final],
                sentences[group[0]].heading_path,
                tokenizer,
            )
        )
    covered = {i for group in groups for i in group}
    if covered != set(range(len(sentences))):
        raise RuntimeError("Sentence coverage invariant failed")
    return result
