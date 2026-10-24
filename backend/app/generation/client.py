import asyncio
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from langchain_core.rate_limiters import InMemoryRateLimiter
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.generation.citations import validate_citations
from backend.app.generation.prompts import INSTRUCTIONS, evidence_prompt
from backend.app.retrieval.service import Retrieved
from backend.app.schemas import GeneratedAnswer


def provider_error(exc: Exception, fallback: str = "generation_unavailable") -> AppError:
    if isinstance(exc, AppError):
        return exc
    cause: BaseException = exc
    while cause.__cause__ is not None and not isinstance(
        cause, (errors.APIError, httpx.RequestError, TimeoutError)
    ):
        cause = cause.__cause__
    if isinstance(cause, (httpx.TimeoutException, TimeoutError)) or (
        isinstance(cause, errors.APIError) and cause.code in {408, 504}
    ):
        return AppError("generation_timeout", "A Gemini request timed out.", 504)
    if isinstance(cause, errors.APIError):
        details = cause.details if isinstance(cause.details, dict) else {}
        error_details = details.get("error", {}).get("details", []) or []
        if cause.code in {401, 403} or (
            cause.code == 400
            and any(item.get("reason") == "API_KEY_INVALID" for item in error_details)
        ):
            return AppError("generation_authentication", "Provider credentials were rejected.", 503)
        if cause.code == 429:
            daily = any(
                "perday"
                in (v.get("quotaId", "") + v.get("quotaMetric", "")).lower().replace("_", "")
                for item in error_details
                for v in item.get("violations", [])
            )
            return AppError(
                "generation_quota_exhausted" if daily else "generation_rate_limited",
                "Gemini daily quota exhausted; wait for the quota reset before a new run."
                if daily
                else "Gemini request quota exceeded; check AI Studio limits and lower "
                "GEMINI_REQUESTS_PER_MINUTE before a new run.",
                429,
            )
        if cause.code == 404:
            return AppError(
                "generation_model_unavailable",
                "The configured Gemini model is unavailable to this project.",
                503,
            )
    return AppError(
        fallback,
        "The evaluation step failed; inspect server diagnostics."
        if fallback.startswith("evaluation_")
        else "The Gemini request failed; check provider access and limits.",
        502,
    )


class Generator:
    def __init__(self, settings: Settings, client: Any = None):
        self.settings = settings
        key = settings.gemini_api_key.get_secret_value()
        self.client = (
            client
            if client is not None
            else (
                genai.Client(
                    api_key=key,
                    vertexai=False,
                    http_options=types.HttpOptions(
                        timeout=max(1, int(settings.generation_timeout_seconds * 1000)),
                        retry_options=types.HttpRetryOptions(attempts=1),
                        async_client_args={"transport": httpx.AsyncHTTPTransport()},
                    ),
                ).aio
                if key
                else None
            )
        )
        self.semaphore = asyncio.Semaphore(settings.generation_concurrency)
        self.rate_limiter = InMemoryRateLimiter(
            requests_per_second=settings.gemini_requests_per_minute / 60,
            check_every_n_seconds=0.01,
            max_bucket_size=1,
        )

    async def answer(
        self, question: str, sources: list[Retrieved]
    ) -> tuple[GeneratedAnswer, dict[str, int]]:
        if self.client is None:
            raise AppError(
                "generation_not_configured",
                "Answer generation needs a server-side Gemini API key.",
                503,
            )
        prompt = evidence_prompt(question, sources)
        usage = {"input_tokens": 0, "output_tokens": 0}
        async with self.semaphore:
            for attempt in range(2):
                try:
                    await self.rate_limiter.aacquire()
                    response = await self.client.models.generate_content(
                        model=self.settings.gemini_generation_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=INSTRUCTIONS,
                            response_mime_type="application/json",
                            response_json_schema=GeneratedAnswer.model_json_schema(),
                        ),
                    )
                    if response.usage_metadata:
                        usage["input_tokens"] += response.usage_metadata.prompt_token_count or 0
                        usage["output_tokens"] += (
                            response.usage_metadata.candidates_token_count or 0
                        )
                    candidates = response.candidates or []
                    if (response.prompt_feedback and response.prompt_feedback.block_reason) or any(
                        c.finish_reason
                        in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
                        for c in candidates
                    ):
                        raise AppError(
                            "generation_refused", "The provider declined this request.", 502
                        )
                    if not candidates or candidates[0].finish_reason != "STOP" or not response.text:
                        raise AppError(
                            "generation_invalid_schema",
                            "The provider returned an incomplete answer.",
                            502,
                        )
                    answer = GeneratedAnswer.model_validate_json(response.text)
                    validate_citations(answer, {s.citation.source_id for s in sources})
                    return answer, usage
                except (errors.APIError, httpx.RequestError, TimeoutError) as exc:
                    raise provider_error(exc) from exc
                except (ValidationError, AppError) as exc:
                    if isinstance(exc, AppError) and exc.code == "generation_refused":
                        raise
                    if attempt:
                        if isinstance(exc, AppError):
                            raise
                        raise AppError(
                            "generation_invalid_schema", "The generated answer is invalid.", 502
                        ) from exc
                    code = exc.code if isinstance(exc, AppError) else "generation_invalid_schema"
                    prompt = evidence_prompt(question, sources) + (
                        f"\nPrevious attempt failed validation: {code}. Return a valid schema with "
                        "exactly matching inline citations and source IDs, "
                        "or abstain without citations."
                    )
        raise RuntimeError("Unreachable generation state")

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
