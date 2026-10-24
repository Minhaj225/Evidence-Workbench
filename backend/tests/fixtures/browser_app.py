"""Isolated browser fixture. Never used by the production entrypoint."""

import os
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI

from backend.app.config import Settings
from backend.app.generation.client import Generator
from backend.app.main import create_app
from backend.app.schemas import GeneratedAnswer
from backend.tests.fixtures.adapters import FakeEmbeddings, FakeReranker
from backend.tests.fixtures.report import seed_report


class FixtureProvider:
    def __init__(self):
        self.responses = self

    async def parse(self, **kwargs):
        unsupported = "president of Mars" in kwargs["input"]
        answer = GeneratedAnswer(
            answer=(
                "Insufficient evidence in the supplied documents."
                if unsupported
                else "The functions are GOVERN, MAP, MEASURE, and MANAGE. [S1]"
            ),
            used_source_ids=[] if unsupported else ["S1"],
            insufficient_context=unsupported,
        )
        return SimpleNamespace(
            output_parsed=answer,
            output=[],
            status="completed",
            usage=SimpleNamespace(input_tokens=20, output_tokens=15),
        )

    async def close(self):
        pass


def create_fixture_app() -> FastAPI:
    if os.environ.get("APP_ENV") != "test":
        raise RuntimeError("Browser fixtures require APP_ENV=test")
    settings = Settings()
    seed_report(settings)
    # Explicit fake adapters avoid network and make browser assertions deterministic.
    np.random.seed(42)
    return create_app(
        settings,
        embedder=FakeEmbeddings(),
        reranker=FakeReranker(),
        generator=Generator(settings, FixtureProvider()),
    )
