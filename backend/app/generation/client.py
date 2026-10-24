import asyncio
from typing import Any

from openai import (
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
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
        key = settings.openai_api_key.get_secret_value()
        self.client = (
            client
            if client is not None
            else (
                AsyncOpenAI(api_key=key, timeout=settings.generation_timeout_seconds, max_retries=0)
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
                "generation_not_configured", "Answer generation needs a server-side API key.", 503
            )
        prompt = evidence_prompt(question, sources)
        usage = {"input_tokens": 0, "output_tokens": 0}
        async with self.semaphore:
            for attempt in range(2):
                try:
                    response = await self.client.responses.parse(
                        model=self.settings.openai_generation_model,
                        instructions=INSTRUCTIONS,
                        input=prompt,
                        text_format=GeneratedAnswer,
                        store=False,
                    )
                    if response.usage:
                        usage["input_tokens"] += response.usage.input_tokens
                        usage["output_tokens"] += response.usage.output_tokens
                    if any(
                        getattr(part, "type", "") == "refusal"
                        for item in response.output
                        for part in getattr(item, "content", [])
                    ):
                        raise AppError(
                            "generation_refused", "The provider declined this request.", 502
                        )
                    if response.status != "completed" or response.output_parsed is None:
                        raise AppError(
                            "generation_invalid_schema",
                            "The provider returned an incomplete answer.",
                            502,
                        )
                    answer = GeneratedAnswer.model_validate(response.output_parsed)
                    validate_citations(answer, {s.citation.source_id for s in sources})
                    return answer, usage
                except APITimeoutError as exc:
                    raise AppError(
                        "generation_timeout", "Answer generation timed out.", 504
                    ) from exc
                except RateLimitError as exc:
                    raise AppError(
                        "generation_rate_limited", "The provider is busy; try again later.", 429
                    ) from exc
                except AuthenticationError as exc:
                    raise AppError(
                        "generation_authentication", "Provider credentials were rejected.", 503
                    ) from exc
                except APIError as exc:
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
            await self.client.close()
