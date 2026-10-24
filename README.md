# Evidence Workbench

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/download/releases/3.12/)
[![Docker](https://img.shields.io/badge/Docker-OK-2496ED.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/anthropic/evaluation-driven-rag/actions)
[![Code style](https://img.shields.io/badge/code%20style-ruff-ff69b4.svg)](https://github.com/astral-sh/ruff)

An evaluation-driven document QA application. Upload text-bearing PDFs or UTF-8 text files, compare fixed-chunk retrieval with semantic chunking + reranking, inspect page citations, and run reproducible NIST benchmarks.

> **Note**: Passing implementation tests does not establish that the enhanced strategy improves retrieval or that generated answers are faithful. See measured results below and preserved reports.

---

## Quick Start

### With Docker (recommended)

```sh
cp .env.example .env
# Configure OPENAI_API_KEY in .env locally; never commit it.
docker compose up -d --build --wait
```

Open [http://localhost:8080](http://localhost:8080). On Documents, open **Demo corpus setup**, then **Load demo corpus**. Wait for both publications to become ready.

### Local Development

```sh
make setup              # Install dependencies
make dev                # Start API and web dev server
```

- API: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Web: [http://127.0.0.1:8080](http://127.0.0.1:8080)

---

## Available Scripts

| Script | Description |
|---|---|
| `make setup` | Install dependencies (uv sync + frontend CI) |
| `make dev` | Start Qdrant, API, and web dev server |
| `make corpus` | Download NIST corpus |
| `make ingest-demo` | Ingest demo documents via API |
| `make benchmark` | Run evaluation benchmark |
| `make lint` | Run linters and type checks |
| `make test` | Run backend tests (85% coverage gate) |
| `make reset-demo` | Reset demo documents |

See [`Makefile`](Makefile) for full list.

---

## Architecture

```mermaid
flowchart LR
    Browser[React application] --> API[FastAPI]
    API --> DB[(SQLite: documents/jobs/runs)]
    API --> Queue[Single persistent job queue]
    Queue --> Parse[Page-aware parsing and cleaning]
    Parse --> Fixed[512-token fixed windows]
    Parse --> Semantic[Sentence-based semantic chunks]
    Fixed --> Embed[BGE CPU embeddings]
    Semantic --> Embed
    Embed --> Vectors[(Qdrant: two collections)]
    API --> Retrieve[Dense search and optional MiniLM reranking]
    Vectors --> Retrieve
    Retrieve --> Generate[OpenAI Responses and citation validation]
    Generate --> Browser
    Queue --> Evaluate[Frozen dataset and report artifacts]
```

---

## Configuration

All application variables and defaults are in [` .env.example`](.env.example). See [configuration details](docs/configuration.md) for their purpose.

Key settings:
- `QDRANT_URL=http://qdrant:6333` — Compose default; local needs `http://127.0.0.1:6333`
- `OPENAI_GENERATION_MODEL=gpt-6-luna` — follows the plan; override for available models
- `OPENAI_EVALUATOR_MODEL=gpt-6.1-sol` — follows the plan

---

## Measured Results

Production run `d2905419-562e-4be8-b882-edf9342507a4`, started 2026-10-19.

| Metric | Baseline | Enhanced | Delta |
|---|---:|---:|---:|
| hit_rate_at_5 | 0.5667 | 0.9000 | +0.3333 |
| precision_at_5 | 0.1200 | 0.1867 | +0.0667 |
| recall_at_5 | 0.5167 | 0.8167 | +0.3000 |
| mrr_at_5 | 0.3244 | 0.7833 | +0.4589 |

- **HitRate@5**: 17/30 → 27/30 (paired 95% bootstrap gain: +0.1333 to +0.5333)
- Median retrieval latency: 61.5 ms (baseline) vs 2679.3 ms (enhanced)
- Cross-encoder reranking accounts for most enhanced latency

[Full report](artifacts/evaluations/d2905419-562e-4be8-b882-edf9342507a4/report.md) · [Run JSON](artifacts/evaluations/d2905419-562e-4be8-b882-edf9342507a4/run.json) · [Verification analysis](docs/verification.md). Artifacts are git-ignored; export with a release if sharing.

---

## Limitations

- Born-digital English text only — no OCR, multilingual guarantee, or authentication
- PDFs may contain hostile instructions; evidence treated as untrusted text
- CPU latency reflects one host; BGE's 512-position limit includes special tokens
- Semantic chunking not guaranteed to improve every corpus

---

## Source & Dependency Licenses

- NIST publications: retained notices, downloaded from NIST, not redistributed
- PyMuPDF: AGPL/commercial terms — review upstream terms before distributing a hosted derivative
- BGE and MiniLM: licenses remain those of their respective model repositories

---

## Troubleshooting

- Failed document: choose same file to retry; repeated encrypted/scanned/invalid PDFs need valid text-bearing source
- Missing dependency at startup: restore Qdrant/model access and restart API
- Evaluation rejects missing/stale corpus versions: re-run demo ingestion, wait for ready, start new run
- Provider auth/timeout/rate-limit/schema errors: correct configuration and run new benchmark
- `make reset-demo`: deletes only documents whose hashes match the pinned manifest; other uploads remain

---

## GitHub Actions

This repository uses GitHub Actions for CI. See `.github/workflows/` for CI configuration.

---

## License

MIT. NIST publications retain their own notices.