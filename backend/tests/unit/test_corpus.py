import hashlib

import httpx
import pytest

from scripts.download_corpus import download


def test_download_verification_and_reuse(tmp_path, pdf_bytes):
    entry = {
        "id": "fixture",
        "local_filename": "test.pdf",
        "pages": 1,
        "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "source_url": "https://nvlpubs.nist.gov/nistpubs/ai/test.pdf",
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=pdf_bytes))
    ) as client:
        target = download(entry, tmp_path, client)
        original_time = target.stat().st_mtime_ns
        assert download(entry, tmp_path, client).stat().st_mtime_ns == original_time
        entry["sha256"] = "0" * 64
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            download(entry, tmp_path, client)
        assert target.read_bytes() == pdf_bytes


def test_bad_download_cleans_temp(tmp_path):
    entry = {
        "id": "fixture",
        "local_filename": "test.pdf",
        "pages": 1,
        "sha256": "0" * 64,
        "source_url": "https://nvlpubs.nist.gov/nistpubs/ai/test.pdf",
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"bad"))
    ) as client:
        with pytest.raises(ValueError, match="SHA-256"):
            download(entry, tmp_path, client)
    assert list(tmp_path.iterdir()) == []
