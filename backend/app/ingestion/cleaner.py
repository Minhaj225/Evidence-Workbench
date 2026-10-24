import math
import re
import unicodedata
from collections import defaultdict

from backend.app.chunking.types import SourceBlock

PARSER_VERSION = "pymupdf-nfc-v1"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"([^\W\d_])-\n[ \t]*([a-z])", r"\1\2", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def match_normalize(text: str) -> str:
    return " ".join(normalize(text).casefold().split())


def candidate_key(text: str) -> str:
    return re.sub(r"\b\d+\b", "#", match_normalize(text))


def clean_blocks(blocks: list[SourceBlock], page_count: int) -> list[SourceBlock]:
    candidates: dict[tuple[str, str], set[int]] = defaultdict(set)
    identities: dict[int, tuple[str, str]] = {}
    for i, block in enumerate(blocks):
        block.text = normalize(block.text)
        if not any(c.isalnum() for c in block.text):
            block.kind = "ignored"
        if block.bbox and block.page_height and len(block.text) <= 160:
            position = (
                "header"
                if block.bbox[1] <= block.page_height * 0.12
                else "footer"
                if block.bbox[3] >= block.page_height * 0.88
                else None
            )
            if position and block.kind != "ignored":
                key = (position, candidate_key(block.text))
                candidates[key].add(block.page_number)
                identities[i] = key
    # A title page is unique when none of its margin strings recur later.
    first_keys = {key for key, pages in candidates.items() if 1 in pages}
    unique_title = bool(first_keys) and all(len(candidates[key]) == 1 for key in first_keys)
    denominator = page_count - int(unique_title)
    for i, key in identities.items():
        pages = candidates[key] - ({1} if unique_title else set())
        if len(pages) >= max(3, math.ceil(0.6 * denominator)):
            blocks[i].kind = key[0]
    offset = 0
    for i, block in enumerate(blocks):
        if (
            block.kind == "body"
            and len(block.text) < 100
            and "\n" not in block.text
            and not block.text.endswith((".", "?", "!", ":", ";"))
            and i + 1 < len(blocks)
            and len(blocks[i + 1].text) > len(block.text)
        ):
            block.kind = "heading"
        block.source_start = offset
        block.source_end = offset + len(block.text)
        offset = block.source_end + 2
    return blocks
