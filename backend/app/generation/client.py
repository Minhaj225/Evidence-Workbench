import asyncio
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.generation.citations import validate_citations
from backend.app.generation.prompts import INSTRUCTIONS, evidence_prompt
from backend.app.retrieval.service import Retrieved
from backend.app.schemas import GeneratedAnswer


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
                except (httpx.TimeoutException, TimeoutError) as exc:
                    raise AppError(
                        "generation_timeout", "Answer generation timed out.", 504
                    ) from exc
                except errors.APIError as exc:
                    if exc.code in {408, 504}:
                        raise AppError(
                            "generation_timeout", "Answer generation timed out.", 504
                        ) from exc
                    if exc.code == 429:
                        raise AppError(
                            "generation_rate_limited",
                            "Gemini quota exceeded; wait and try again later.",
                            429,
                        ) from exc
                    if exc.code in {401, 403}:
                        raise AppError(
                            "generation_authentication", "Provider credentials were rejected.", 503
                        ) from exc
                    raise AppError(
                        "generation_unavailable", "The generation provider is unavailable.", 502
                    ) from exc
                except httpx.RequestError as exc:
                    raise AppError(
                        "generation_unavailable", "The generation provider is unavailable.", 502
                    ) from exc
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
