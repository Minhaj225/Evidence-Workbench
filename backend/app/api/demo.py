import asyncio
import json

import httpx
from fastapi import APIRouter, Request, UploadFile

from backend.app.errors import AppError
from scripts.download_corpus import ROOT, download

router = APIRouter(prefix="/api/demo", tags=["demo"])


def download_sources() -> list:
    manifest = json.loads((ROOT / "corpus/manifest.json").read_text())
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        return [download(entry, ROOT / "data/corpus", client) for entry in manifest["documents"]]


@router.post("", status_code=202)
async def load_demo(request: Request) -> list[dict]:
    try:
        paths = await asyncio.to_thread(download_sources)
    except (OSError, ValueError, httpx.HTTPError) as exc:
        raise AppError(
            "corpus_download_failed", "The pinned corpus could not be verified.", 503
        ) from exc
    records = []
    for path in paths:
        with path.open("rb") as source:
            record, _ = await request.app.state.documents.upload(
                UploadFile(file=source, filename=path.name), retry_failed=True
            )
            records.append(record)
    return records
