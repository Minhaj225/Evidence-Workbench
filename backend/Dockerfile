FROM python:3.12.15-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.28
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev
COPY backend ./backend
COPY scripts ./scripts
COPY corpus ./corpus
COPY evaluation ./evaluation
RUN useradd --uid 10001 --create-home rag && mkdir -p data artifacts/evaluations /models && chown -R rag:rag data artifacts /models
ENV PATH="/app/.venv/bin:$PATH" HF_HOME=/models PYTHONUNBUFFERED=1 RAGAS_DO_NOT_TRACK=true
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
