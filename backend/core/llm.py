from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import functools
import json
import logging
import random
from typing import Any, ParamSpec, TypeVar

from core.config import get_settings
from core.redis_client import cache_get
from core.redis_client import cache_set
from core.redis_client import make_cache_key


logger = logging.getLogger(__name__)
settings = get_settings()

P = ParamSpec("P")
T = TypeVar("T")
GEMINI_CACHE_TTL_SECONDS = 24 * 60 * 60


def with_exponential_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("with_exponential_backoff can only wrap async callables")

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    if attempt == max_retries - 1:
                        raise

                    delay = min(max_delay, base_delay * (2**attempt))
                    if jitter and delay > 0:
                        delay += random.uniform(0, delay * 0.5)

                    logger.warning(
                        "Retrying %s on attempt %s/%s in %.2fs after error: %s",
                        func.__qualname__,
                        attempt + 1,
                        max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

            raise RuntimeError("unreachable")

        return wrapper

    return decorator


class GeminiClient:
    @with_exponential_backoff()
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        use_cache: bool = True,
    ) -> str:
        cache_key = make_cache_key(
            "gemini",
            "complete",
            settings.gemini_flash_model,
            system or "",
            prompt,
        )
        if use_cache:
            cached_value = await cache_get(cache_key)
            if isinstance(cached_value, str):
                return cached_value

        def _run() -> str:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(
                settings.gemini_flash_model,
                system_instruction=system or None,
            )
            response = model.generate_content(prompt)
            text = getattr(response, "text", None)
            if not text:
                raise ValueError("Gemini returned an empty response")
            return text.strip()

        result = await asyncio.to_thread(_run)
        if use_cache:
            await cache_set(cache_key, result, GEMINI_CACHE_TTL_SECONDS)
        return result

    @with_exponential_backoff()
    async def embed(self, text: str) -> list[float]:
        def _run() -> list[float]:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            response = genai.embed_content(
                model=settings.gemini_embedding_model,
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            embedding = self._extract_embedding(response)
            if not embedding:
                raise ValueError("Gemini returned an empty embedding")
            return [float(value) for value in embedding]

        return await asyncio.to_thread(_run)

    @staticmethod
    def _extract_embedding(response: Any) -> list[float] | None:
        if isinstance(response, dict):
            embedding = response.get("embedding")
            if isinstance(embedding, dict):
                values = embedding.get("values")
                if isinstance(values, list):
                    return values
            if isinstance(embedding, list):
                return embedding

        embedding = getattr(response, "embedding", None)
        if isinstance(embedding, dict):
            values = embedding.get("values")
            if isinstance(values, list):
                return values
        values = getattr(embedding, "values", None)
        if isinstance(values, list):
            return values
        if isinstance(embedding, list):
            return embedding
        return None


class GroqClient:
    def __init__(self) -> None:
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

    @with_exponential_backoff()
    async def complete(self, prompt: str, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self._get_client().chat.completions.create(
            model="llama3-8b-8192",
            messages=messages,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response")
        return content.strip()


class LLMClient:
    def __init__(self) -> None:
        self._gemini = GeminiClient()
        self._groq = GroqClient()

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        use_cache: bool = True,
    ) -> str:
        try:
            return await self._gemini.complete(
                prompt=prompt,
                system=system,
                use_cache=use_cache,
            )
        except Exception as exc:
            logger.exception("Gemini completion failed, falling back to Groq: %s", exc)
            return await self._groq.complete(prompt=prompt, system=system)

    async def embed(self, text: str) -> list[float]:
        return await self._gemini.embed(text)


class HallucinationScorer:
    CRITERIA: list[tuple[str, str]] = [
        ("company_name_match", "The company name matches the source data."),
        ("role_title_match", "The role title matches the source data."),
        ("skills_grounded", "Claimed skills are grounded in the job or resume data."),
        ("resume_consistency", "The output is consistent with the candidate resume."),
        ("contact_accuracy", "Contact details are accurate and not fabricated."),
        ("score_range_valid", "Numeric scores and ranges stay within valid bounds."),
    ]

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def score(self, output: Any, source_data: Any) -> dict[str, Any]:
        score = 0
        breakdown: dict[str, dict[str, Any]] = {}
        serialized_output = json.dumps(output, default=str, ensure_ascii=False)
        serialized_source = json.dumps(source_data, default=str, ensure_ascii=False)

        for key, description in self.CRITERIA:
            prompt = (
                "Evaluate a generated job-application artifact against one criterion.\n"
                f"Criterion key: {key}\n"
                f"Criterion description: {description}\n\n"
                "Source data:\n"
                f"{serialized_source}\n\n"
                "Generated output:\n"
                f"{serialized_output}\n\n"
                "Reply in one line starting with PASS or FAIL, followed by a reason."
            )
            response = await self._client.complete(
                prompt=prompt,
                system="You are a strict factual verifier for job-application data.",
                use_cache=False,
            )
            passed, reason = self._parse_response(response)
            breakdown[key] = {
                "description": description,
                "passed": passed,
                "reason": reason,
                "raw_response": response,
            }
            if passed:
                score += 1

        max_score = len(self.CRITERIA)
        passed = (score / max_score) >= settings.hallucination_threshold
        return {
            "score": score,
            "max_score": max_score,
            "breakdown": breakdown,
            "passed": passed,
        }

    @staticmethod
    def _parse_response(response: str) -> tuple[bool, str]:
        normalized = response.strip()
        upper_normalized = normalized.upper()

        if upper_normalized.startswith("PASS"):
            return True, HallucinationScorer._extract_reason(normalized, prefix="PASS")
        if upper_normalized.startswith("FAIL"):
            return False, HallucinationScorer._extract_reason(normalized, prefix="FAIL")
        return False, f"Malformed response: {normalized}"

    @staticmethod
    def _extract_reason(response: str, prefix: str) -> str:
        remainder = response[len(prefix) :].lstrip(" :-")
        return remainder or "No reason provided."


llm_client = LLMClient()
hallucination_scorer = HallucinationScorer(llm_client)


__all__ = [
    "GeminiClient",
    "GroqClient",
    "HallucinationScorer",
    "LLMClient",
    "hallucination_scorer",
    "llm_client",
    "with_exponential_backoff",
]
