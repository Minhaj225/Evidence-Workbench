from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from qdrant_client import QdrantClient

from backend.app.config import Settings
from backend.app.retrieval.vector_store import VectorStore
from backend.tests.fixtures.adapters import FakeEmbeddings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path}/app.db",
        document_root=tmp_path / "documents",
        page_cache_root=tmp_path / "pages",
        artifact_root=tmp_path / "artifacts",
        openai_api_key="",
    )


@pytest.fixture
def embedder():
    return FakeEmbeddings()


@pytest.fixture
def tokenizer(embedder):
    return embedder.tokenizer


@pytest.fixture
def store(settings):
    store = VectorStore(settings, QdrantClient(":memory:"))
    store.ensure_collections()
    yield store
    store.client.close()


@pytest.fixture
def document_id():
    return str(uuid4())


@pytest.fixture
def pdf_bytes():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        text = "The four core functions are GOVERN, MAP, MEASURE, and MANAGE. " * 7
        page.insert_textbox(pymupdf.Rect(40, 60, 550, 700), text)
        return pdf.tobytes()


@pytest.fixture
def text_file(tmp_path):
    path = Path(tmp_path) / "source.txt"
    path.write_text(
        "Core functions\n\nGOVERN establishes policies. MAP describes context. "
        "MEASURE assesses risks. MANAGE prioritizes responses."
    )
    return path
