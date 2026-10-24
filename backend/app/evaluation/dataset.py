import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import pymupdf
from pydantic import BaseModel, ConfigDict, Field

from backend.app.errors import AppError
from backend.app.ingestion.cleaner import normalize
from scripts.download_corpus import ROOT, verify


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    page: int = Field(ge=1)
    text: str = Field(min_length=20)


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    answerable: bool
    question: str = Field(min_length=3, max_length=2000)
    reference_answer: str = Field(min_length=1)
    topic: str
    question_type: Literal[
        "definition",
        "enumeration",
        "relationship",
        "recommended_action",
        "table",
        "synthesis",
        "unanswerable",
    ]
    difficulty: Literal["easy", "medium", "hard"]
    corpus_group: Literal["100", "600", "synthesis", "unanswerable"]
    evidence: list[Evidence]


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_dataset(root: Path = ROOT) -> tuple[list[Case], dict[str, Any], str, str]:
    try:
        path, manifest_path = root / "evaluation/dataset.jsonl", root / "corpus/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        if manifest["schema_version"] != 1:
            raise ValueError("Manifest version")
        documents = {d["id"]: d for d in manifest["documents"]}
        cases = [
            Case.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
        ]
        answerable = [case for case in cases if case.answerable]
        if len(cases) != 35 or len({c.id for c in cases}) != 35 or len(answerable) != 30:
            raise ValueError(
                "Dataset must contain 30 answerable and five unanswerable unique cases"
            )
        if Counter(c.question_type for c in answerable) != dict.fromkeys(
            [
                "definition",
                "enumeration",
                "relationship",
                "recommended_action",
                "table",
                "synthesis",
            ],
            5,
        ):
            raise ValueError("Question type distribution")
        if Counter(c.difficulty for c in answerable) != {"easy": 10, "medium": 12, "hard": 8}:
            raise ValueError("Difficulty distribution")
        if Counter(c.corpus_group for c in answerable) != {"100": 12, "600": 12, "synthesis": 6}:
            raise ValueError("Corpus distribution")
        pages: dict[tuple[str, int], str] = {}
        for doc in documents.values():
            source = root / "data/corpus" / doc["local_filename"]
            verify(source, doc)
            with pymupdf.open(source) as pdf:
                for index, page in enumerate(pdf, 1):
                    pages[(doc["id"], index)] = " ".join(
                        normalize(
                            "\n\n".join(
                                block[4]
                                for block in page.get_text("blocks", sort=True)
                                if block[6] == 0
                            )
                        ).split()
                    )
        for case in cases:
            if case.answerable != bool(case.evidence):
                raise ValueError(f"Evidence presence: {case.id}")
            if not case.answerable and case.question_type != "unanswerable":
                raise ValueError(f"Unanswerable type: {case.id}")
            if case.corpus_group == "synthesis" and len(case.evidence) < 2:
                raise ValueError(f"Synthesis requires separate evidence: {case.id}")
            for evidence in case.evidence:
                if evidence.document_sha256 != documents[evidence.document_id]["sha256"]:
                    raise ValueError(f"Evidence digest: {case.id}")
                text = " ".join(normalize(evidence.text).split())
                count = pages[(evidence.document_id, evidence.page)].count(text)
                if count == 0 or (count > 1 and len(case.evidence) < 2):
                    raise ValueError(f"Evidence absent or ambiguous: {case.id}")
        return cases, manifest, file_digest(path), file_digest(manifest_path)
    except (ValueError, KeyError, OSError) as exc:
        raise AppError(
            "evaluation_dataset_invalid", "Corpus or evaluation dataset validation failed."
        ) from exc
