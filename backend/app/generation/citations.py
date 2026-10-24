import re

from backend.app.errors import AppError
from backend.app.schemas import GeneratedAnswer


def validate_citations(answer: GeneratedAnswer, supplied: set[str]) -> None:
    markers = set(re.findall(r"\[S(\d+)\]", answer.answer))
    sources = {f"S{number}" for number in markers}
    valid = (
        sources == set(answer.used_source_ids)
        and sources <= supplied
        and sources <= {"S1", "S2", "S3", "S4", "S5"}
    )
    valid = valid and (bool(sources) if not answer.insufficient_context else not sources)
    if not valid:
        raise AppError(
            "generation_invalid_citations", "The generated citations could not be verified.", 502
        )
