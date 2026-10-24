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
| `OPENAI_API_KEY` | `` | Server-side provider secret |
| `OPENAI_GENERATION_MODEL` | `gpt-6-luna` | Answer generation model |
| `OPENAI_EVALUATOR_MODEL` | `gpt-6.1-sol` | Evaluation judge model |
| `MAX_UPLOAD_BYTES` | `20971520` | Maximum input file bytes |
| `MAX_PDF_PAGES` | `300` | Maximum physical PDF pages |
| `MAX_QUESTION_CHARS` | `2000` | Maximum trimmed question characters |
| `MAX_SELECTED_DOCUMENTS` | `20` | Maximum explicitly selected documents |
| `GENERATION_TIMEOUT_SECONDS` | `60.0` | Provider timeout in seconds |
| `GENERATION_CONCURRENCY` | `4` | Concurrent generation requests |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated exact frontend origins |
| `LOG_LEVEL` | `INFO` | Structured log level |

Additional operational variables: `HF_HOME` controls the local model cache; `HF_HUB_OFFLINE=1` requires already-cached models; `API_URL` selects the CLI/development proxy target; `TEST_QDRANT_URL` enables real integration tests; `RUN_LIVE_OPENAI_TESTS=1` enables the hosted smoke test; `E2E_URL` selects the browser-test target; `CHROME_PATH` optionally selects an installed Chromium executable.

The API sends no original PDFs to the generation provider. Generation sends the question and retrieved passages; evaluation additionally sends reference answers and contexts. Requests specify `store=false`.
