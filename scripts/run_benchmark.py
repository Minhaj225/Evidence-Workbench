import argparse
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the immutable 35-case benchmark through the API"
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.api_url, timeout=120) as client:
        response = client.post("/api/evaluations")
        response.raise_for_status()
        run_id = response.json()["id"]
        print(f"Benchmark run: {run_id}", flush=True)
        while True:
            response = client.get(f"/api/evaluations/{run_id}")
            response.raise_for_status()
            run = response.json()
            if run["status"] in {"completed", "failed"}:
                print(f"{run['status']}: artifacts/evaluations/{run_id}")
                if run["error_code"]:
                    print(run["error_code"])
                raise SystemExit(0 if run["status"] == "completed" else 1)
            time.sleep(2)


if __name__ == "__main__":
    main()
