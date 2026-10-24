import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from backend.app.ingestion.parser import validate_pdf

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 30 * 1024 * 1024


def verify(path: Path, entry: dict[str, Any]) -> None:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"{entry['id']}: download size limit exceeded")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != entry["sha256"]:
        raise ValueError(f"{entry['id']}: SHA-256 mismatch (received {digest})")
    if validate_pdf(path, entry["pages"]) != entry["pages"]:
        raise ValueError(f"{entry['id']}: page count mismatch")


def download(entry: dict[str, Any], target_dir: Path, client: httpx.Client) -> Path:
    filename = entry["local_filename"]
    if Path(filename).name != filename or not filename.endswith(".pdf"):
        raise ValueError("Manifest filename must be a PDF basename")
    if not entry["source_url"].startswith("https://nvlpubs.nist.gov/nistpubs/ai/"):
        raise ValueError("Corpus source must be the pinned NIST publication host")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    if target.exists():
        verify(target, entry)
        return target
    fd, temporary = tempfile.mkstemp(prefix=".corpus-", dir=target_dir)
    path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as output, client.stream("GET", entry["source_url"]) as response:
            response.raise_for_status()
            size = 0
            for data in response.iter_bytes(65536):
                size += len(data)
                if size > MAX_BYTES:
                    raise ValueError(f"{entry['id']}: download size limit exceeded")
                output.write(data)
        verify(path, entry)
        os.replace(path, target)
    finally:
        path.unlink(missing_ok=True)
    return target


def main() -> None:
    manifest = json.loads((ROOT / "corpus/manifest.json").read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported corpus manifest version")
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        for entry in manifest["documents"]:
            path = download(entry, ROOT / "data/corpus", client)
            print(f"Verified {entry['id']}: {entry['pages']} pages ({path.name})")


if __name__ == "__main__":
    main()
