UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
HF_HOME ?= $(CURDIR)/.cache/huggingface
export UV_CACHE_DIR HF_HOME
API_URL ?= http://127.0.0.1:8000
.PHONY: setup dev format lint test test-integration test-e2e corpus warm-models ingest-demo benchmark compose-up compose-down reset-demo
setup:
	uv sync --locked
	npm --prefix frontend ci
dev:
	@echo 'Start Qdrant: docker compose up -d qdrant'
	@echo 'API: QDRANT_URL=http://127.0.0.1:6333 uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log'
	@echo 'Web (separate terminal): npm --prefix frontend run dev'
format:
	uv run ruff format backend scripts
	uv run ruff check backend scripts --fix
	npm --prefix frontend run format
lint:
	uv run ruff format --check backend scripts
	uv run ruff check backend scripts
	uv run mypy backend/app scripts
	npm --prefix frontend run typecheck
	npm --prefix frontend run lint
test:
	uv run pytest -m 'not integration and not live' --cov=backend/app --cov-report=term-missing --cov-report=json --cov-fail-under=85
	uv run python scripts/check_coverage.py
	npm --prefix frontend test
test-integration:
	TEST_QDRANT_URL=$${TEST_QDRANT_URL:-http://127.0.0.1:6333} uv run pytest -m integration
test-e2e:
	npm --prefix frontend run test:e2e
corpus:
	uv run python -m scripts.download_corpus
warm-models:
	uv run python -m scripts.warm_models
ingest-demo:
	uv run python -m scripts.ingest_demo --api-url $(API_URL)
benchmark:
	uv run python -m scripts.run_benchmark --api-url $(API_URL)
compose-up:
	docker compose up -d --build --wait
compose-down:
	docker compose down
reset-demo:
	uv run python -m scripts.reset_demo --api-url $(API_URL)
