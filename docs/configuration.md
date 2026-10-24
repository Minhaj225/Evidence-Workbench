# Configuration

Values are read once at API startup. Keep secrets in a local `.env` or deployment secret store. Do not use frontend environment variables for keys.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Runtime mode |
| `APP_HOST` | `0.0.0.0` | Declared host; the server command selects the bind address |
| `APP_PORT` | `8000` | Declared port; the server command selects the port |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite connection URL |
| `DOCUMENT_ROOT` | `data/documents` | Private originals root |
| `PAGE_CACHE_ROOT` | `data/pages` | Rendered private page cache |
| `ARTIFACT_ROOT` | `artifacts/evaluations` | Immutable benchmark artifacts |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant HTTP endpoint |
| `QDRANT_API_KEY` | `` | Optional Qdrant authentication secret |
| `BASELINE_COLLECTION` | `rag_baseline_v1` | Fixed chunk collection |
| `SEMANTIC_COLLECTION` | `rag_semantic_v1` | Semantic chunk collection |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L6-v2` | Local reranking model |
| `GEMINI_API_KEY` | `` | Server-side provider secret |
| `GEMINI_GENERATION_MODEL` | `gemini-3.5-flash-lite` | Answer generation model |
| `GEMINI_EVALUATOR_MODEL` | `gemini-3.5-flash-lite` | Evaluation judge model |
| `MAX_UPLOAD_BYTES` | `20971520` | Maximum input file bytes |
| `MAX_PDF_PAGES` | `300` | Maximum physical PDF pages |
| `MAX_QUESTION_CHARS` | `2000` | Maximum trimmed question characters |
| `MAX_SELECTED_DOCUMENTS` | `20` | Maximum explicitly selected documents |
| `GENERATION_TIMEOUT_SECONDS` | `60.0` | Provider timeout in seconds |
| `GENERATION_CONCURRENCY` | `1` | Concurrent generation requests |
| `GEMINI_REQUESTS_PER_MINUTE` | `5` | Shared, evenly spaced request budget for generation, repairs, and all judge calls |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated exact frontend origins |
| `LOG_LEVEL` | `INFO` | Structured log level |

Additional operational variables: `HF_HOME` controls the local model cache; `HF_HUB_OFFLINE=1` requires already-cached models; `API_URL` selects the CLI/development proxy target; `TEST_QDRANT_URL` enables real integration tests; `RUN_LIVE_GEMINI_TESTS=1` enables the hosted smoke test; `E2E_URL` selects the browser-test target; `CHROME_PATH` optionally selects an installed Chromium executable.

The API sends no original PDFs to the generation provider. Generation sends the question and retrieved passages; evaluation additionally sends reference answers and contexts. The Gemini Developer API is used directly, with no file upload, search tools, or context caching. Google may use free-tier inputs and outputs to improve its products; see [pricing and data use](https://ai.google.dev/gemini-api/docs/pricing).

## Gemini free-tier setup

1. Create an API key for a free-tier project in [Google AI Studio](https://aistudio.google.com/apikey).
2. Set `GEMINI_API_KEY` in the server's local `.env`. Never place the key in a `VITE_` variable or commit it.
3. Keep `GEMINI_GENERATION_MODEL=gemini-3.5-flash-lite` and `GEMINI_EVALUATOR_MODEL=gemini-3.5-flash-lite`. Google currently lists text input and output for this model as free of charge on the free tier. These replace the previous provider's key and model variables; old variable names are no longer read.
4. With Docker, run `docker compose up -d --build --force-recreate api web` after changing `.env` or code. `docker compose restart` keeps the old container environment. Local development needs an API restart.
5. To test a small grounded answer against the real provider, run `RUN_LIVE_GEMINI_TESTS=1 uv run pytest -m live -q`. This sends only a synthetic launch-year fixture, not your documents.

The application does not enable billing or fall back to a paid model. A model name alone does not enforce free billing: keep the Google project on the free tier. If billing is enabled later, the same model can incur charges.

`GENERATION_CONCURRENCY=1` limits simultaneous answers. `GEMINI_REQUESTS_PER_MINUTE=5` also spaces hosted requests at least 12 seconds apart across answers, citation repairs, Ragas metrics, and citation judging. This budget is shared within the single API process, even when generation and judging use different models. Google enforces per-project request, token, and daily quotas; inspect your actual limits in [AI Studio](https://aistudio.google.com/rate-limit), since they vary by model and project and other applications can consume the same quota. Lower the request budget if necessary. Pacing cannot fix a token or daily quota limit.

Quota errors are reported as `generation_rate_limited` (HTTP 429); a daily quota violation is `generation_quota_exhausted`. After a daily quota, invalid-key, or unavailable-model failure, the benchmark skips remaining hosted requests while completing local retrieval measurements, including after a worker restart. Answer schema/citation repair is limited to one extra request. Ragas can make up to three repair requests for malformed judged output; these also use the shared budget. Transport/provider errors are not automatically retried by either the answer client or the Ragas wrapper.

Evaluation uses Gemini for Ragas faithfulness, context precision/recall, and citation scoring. The 65-case benchmark makes multiple hosted requests per answerable case and can exhaust free-tier quotas; missing or failed scores remain failures in the saved report. Run it separately from interactive use and preserve earlier results. Do not claim Gemini answer quality from the existing retrieval-only benchmark.

At the default pacing, a full benchmark can take over an hour. The evaluation page shows provider errors and how many cases have faithfulness scores. An aggregate judged metric stays unavailable if any required score is missing, even if some cases were judged successfully. New reports include per-metric coverage counts and safe per-case error messages/stages. Existing finalized reports remain unchanged; correcting configuration requires a new run.

Model availability changes. The defaults were checked against Google's [pricing](https://ai.google.dev/gemini-api/docs/pricing) and [model lifecycle](https://ai.google.dev/gemini-api/docs/deprecations) documentation on 2026-10-24. Gemini 2.5 models are restricted to existing users, so they are not the default for a new account.
