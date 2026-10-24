import argparse
import json
import time

import httpx

from scripts.download_corpus import ROOT, verify


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest the verified NIST corpus through the public API"
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "corpus/manifest.json").read_text())
    with httpx.Client(base_url=args.api_url, timeout=60) as client:
        for entry in manifest["documents"]:
            path = ROOT / "data/corpus" / entry["local_filename"]
            verify(path, entry)
            with path.open("rb") as stream:
                response = client.post(
                    "/api/documents",
                    files={"file": (path.name, stream, "application/pdf")},
                    data={"retry_failed": "true"},
                )
            response.raise_for_status()
            doc_id = response.json()["document"]["id"]
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline:
                status = client.get(f"/api/documents/{doc_id}")
                status.raise_for_status()
                document = status.json()["document"]
                if document["status"] == "failed":
                    raise RuntimeError(f"{entry['id']}: {document['error_code']}")
                if document["status"] == "ready":
                    print(
                        f"Ready {entry['id']}: baseline={document['baseline_chunk_count']}, "
                        f"semantic={document['semantic_chunk_count']}, id={doc_id}"
                    )
                    break
                time.sleep(2)
            else:
                raise TimeoutError(f"{entry['id']}: ingestion did not finish within 30 minutes")


if __name__ == "__main__":
    main()
