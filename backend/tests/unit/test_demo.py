from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.fixtures.adapters import FakeReranker


def test_demo_uses_upload_validation(settings, embedder, store, text_file):
    app = create_app(settings, embedder=embedder, reranker=FakeReranker(), store=store)
    with (
        TestClient(app) as client,
        patch("backend.app.api.demo.download_sources", return_value=[text_file]),
    ):
        result = client.post("/api/demo")
        assert result.status_code == 202
        assert result.json()[0]["document"]["original_filename"] == text_file.name
        with patch("backend.app.api.demo.download_sources", side_effect=ValueError("bad hash")):
            result = client.post("/api/demo")
            assert result.status_code == 503
            assert result.json()["error"]["code"] == "corpus_download_failed"
