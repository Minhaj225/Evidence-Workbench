import argparse
import json

import httpx

from scripts.download_corpus import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete only the two pinned demo documents through the API"
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    hashes = {
        entry["sha256"]
        for entry in json.loads((ROOT / "corpus/manifest.json").read_text())["documents"]
    }
    if (
        input("Type DELETE DEMO to remove the two NIST documents and their indexes: ")
        != "DELETE DEMO"
    ):
        print("Cancelled; nothing was deleted.")
        return
    with httpx.Client(base_url=args.api_url, timeout=120) as client:
        response = client.get("/api/documents")
        response.raise_for_status()
        for record in response.json():
            document = record["document"]
            if document["sha256"] in hashes:
                result = client.delete(f"/api/documents/{document['id']}")
                result.raise_for_status()
                print(f"Deleted demo document {document['id']}")


if __name__ == "__main__":
    main()
