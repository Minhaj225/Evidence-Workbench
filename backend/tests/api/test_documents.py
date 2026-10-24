import time
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.fixtures.adapters import FakeReranker


def wait_terminal(client, doc_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(f"/api/documents/{doc_id}").json()
        if result["document"]["status"] in {"ready", "failed"}:
            return result
        time.sleep(0.03)
    raise AssertionError("Ingestion did not finish")


def test_pdf_lifecycle(settings, embedder, store, pdf_bytes):
    app = create_app(settings, embedder=embedder, reranker=FakeReranker(), store=store)
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200 and health.json()["status"] == "degraded"
        response = client.post("/api/documents", files={"file": ("../../fixture.pdf", pdf_bytes)})
        assert response.status_code == 202, response.text
        doc_id = response.json()["document"]["id"]
        assert response.json()["document"]["created_at"].endswith(("Z", "+00:00"))
        ready = wait_terminal(client, doc_id)
        assert ready["document"]["status"] == "ready", ready
        assert ready["document"]["baseline_chunk_count"] > 0
        assert ready["job"]["status"] == "completed"
        duplicate = client.post("/api/documents", files={"file": ("copy.pdf", pdf_bytes)})
        assert duplicate.status_code == 200 and duplicate.json()["deduplicated"]
        page = client.get(f"/api/documents/{doc_id}/pages/1")
        assert page.status_code == 200 and page.content.startswith(b"\x89PNG")
        assert client.get(f"/api/documents/{doc_id}/pages/2").status_code == 422
        assert len(client.get("/api/documents").json()) == 1
        answer = client.post("/api/answers", json={"question": "What are the core functions?"})
        assert (
            answer.status_code == 503
            and answer.json()["error"]["code"] == "generation_not_configured"
        )
        assert client.delete(f"/api/documents/{doc_id}").status_code == 204
        assert client.get(f"/api/documents/{doc_id}").status_code == 404
        assert not (settings.document_root / doc_id).exists()
        assert store.count("baseline", doc_id) == store.count("semantic", doc_id) == 0


def test_api_error_shapes(settings, embedder, store):
    app = create_app(settings, embedder=embedder, reranker=FakeReranker(), store=store)
    with TestClient(app) as client:
        for filename, data, status in [
            ("a.exe", b"abc", 415),
            ("a.pdf", b"bad", 422),
            ("a.txt", b"", 422),
        ]:
            result = client.post("/api/documents", files={"file": (filename, data)})
            assert result.status_code == status
            assert set(result.json()["error"]) == {"code", "message", "request_id", "details"}
            assert result.headers["x-request-id"] == result.json()["error"]["request_id"]
        assert client.post("/api/answers", json={"question": "???"}).status_code == 422
        assert client.post("/api/answers", json={"question": "What happened?"}).status_code == 409
        assert (
            client.post(
                "/api/answers", json={"question": "What happened?", "document_ids": [str(uuid4())]}
            ).status_code
            == 404
        )
        assert client.get("/api/documents/not-a-uuid").status_code == 422


def test_text_preview_and_failed_retry(settings, embedder, store):
    app = create_app(settings, embedder=embedder, reranker=FakeReranker(), store=store)
    with TestClient(app) as client:
        response = client.post(
            "/api/documents", files={"file": ("data.txt", b"Text is supported.")}
        )
        doc_id = response.json()["document"]["id"]
        assert wait_terminal(client, doc_id)["document"]["status"] == "ready"
        assert client.get(f"/api/documents/{doc_id}/pages/1").status_code == 422
        empty = client.post("/api/documents", files={"file": ("empty.txt", b"    ")})
        failed_id = empty.json()["document"]["id"]
        assert wait_terminal(client, failed_id)["document"]["status"] == "failed"
        assert (
            client.post("/api/documents", files={"file": ("empty.txt", b"    ")}).status_code == 409
        )
        retry = client.post(
            "/api/documents", files={"file": ("empty.txt", b"    ")}, data={"retry_failed": "true"}
        )
        assert retry.status_code == 202 and retry.json()["job"]["attempt"] == 2
        wait_terminal(client, failed_id)
