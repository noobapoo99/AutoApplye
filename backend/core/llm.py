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


'''
class GeminiClient:
    @with_exponential_backoff()
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        use_cache: bool = True,
    ) -> str:
        pass

    @with_exponential_backoff()
    async def embed(self, text: str) -> list[float]:
        pass
'''


class OllamaClient:
    def __init__(self) -> None:
        pass

    @with_exponential_backoff()
    async def complete(self, prompt: str, system: str | None = None) -> str:
        import httpx

        url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"].strip()

    @with_exponential_backoff()
    async def embed(self, text: str) -> list[float]:
        import httpx

        url = f"{settings.ollama_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": settings.ollama_embedding_model,
            "prompt": text,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["embedding"]


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
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=2048,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response")
        return content.strip()


# ---------------------------------------------------------------------------
# Pure-Python fallback embedding (bag-of-words / TF-IDF style)
# Used when Ollama is unavailable so the resume agent doesn't crash.
# ---------------------------------------------------------------------------

import hashlib
import math
import re as _re

_EMBED_DIM = 384  # same dim as nomic-embed-text for compatibility


def _tfidf_embed(text: str) -> list[float]:
    """Produce a fixed-dimension pseudo-embedding via hashed bag-of-words."""
    tokens = _re.findall(r"[a-z0-9]+", text.lower())
    vec = [0.0] * _EMBED_DIM
    if not tokens:
        return vec
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        idx = h % _EMBED_DIM
        sign = 1.0 if (h // _EMBED_DIM) % 2 == 0 else -1.0
        vec[idx] += sign
    # L2-normalize
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class LLMClient:
    def __init__(self) -> None:
        # self._gemini = GeminiClient()
        self._groq = GroqClient()
        self._ollama = OllamaClient()

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        use_cache: bool = True,
    ) -> str:
        # Try Groq first, and if it fails (rate limit, etc), fallback to Ollama locally.
        try:
            return await self._groq.complete(prompt=prompt, system=system)
        except Exception as exc:
            logger.warning("Groq completion failed, falling back to Ollama: %s", exc)
            return await self._ollama.complete(prompt=prompt, system=system)

    async def embed(self, text: str) -> list[float]:
        # Try Ollama first; if unavailable use pure-Python fallback
        try:
            return await self._ollama.embed(text)
        except Exception as exc:
            logger.warning(
                "Ollama embed unavailable, using TF-IDF fallback: %s", exc
            )
            return _tfidf_embed(text)


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
        serialized_output = json.dumps(output, default=str, ensure_ascii=False)[:3000]
        serialized_source = json.dumps(source_data, default=str, ensure_ascii=False)[:3000]

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
    # "GeminiClient",
    "GroqClient",
    "OllamaClient",
    "HallucinationScorer",
    "LLMClient",
    "hallucination_scorer",
    "llm_client",
    "with_exponential_backoff",
]
