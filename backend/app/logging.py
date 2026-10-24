import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in (
            "request_id",
            "job_id",
            "document_id",
            "run_id",
            "stage",
            "duration_ms",
            "error_code",
            "error_type",
            "case_id",
            "version",
        ):
            if hasattr(record, key):
                event[key] = getattr(record, key)
        return json.dumps(event)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("rag")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    # HTTP/provider logs can include request URLs or payloads.
    for name in ("httpx", "httpcore", "google.genai", "langchain_google_genai"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
