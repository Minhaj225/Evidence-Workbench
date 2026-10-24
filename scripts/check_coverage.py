"""Enforce the plan's stricter coverage for correctness-critical modules."""

import json
from pathlib import Path


def main() -> None:
    files = json.loads(Path("coverage.json").read_text())["files"]
    paths = (
        "backend/app/chunking/",
        "backend/app/generation/citations.py",
        "backend/app/evaluation/metrics.py",
    )
    for prefix in paths:
        counts = [row["summary"] for path, row in files.items() if path.startswith(prefix)]
        total = sum(row["num_statements"] for row in counts)
        covered = sum(row["covered_lines"] for row in counts)
        if not total or covered / total < 0.90:
            raise SystemExit(f"{prefix}: critical-module coverage is below 90%")
        print(f"{prefix}: {covered / total:.1%}")


if __name__ == "__main__":
    main()
