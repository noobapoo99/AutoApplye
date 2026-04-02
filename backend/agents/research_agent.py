from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import asyncio
import json
import logging
import re
from typing import Any

import httpx

from agents.base import AgentFactory
from agents.base import BaseAgent
from core.config import get_settings
from core.llm import llm_client
from core.llm import with_exponential_backoff
from core.queue import JD_ENRICHED
from core.queue import queue_manager
from core.redis_client import cache_get
from core.redis_client import cache_set
from core.redis_client import make_cache_key


logger = logging.getLogger(__name__)
settings = get_settings()

ONE_DAY_CACHE_TTL_SECONDS = 86400
SYNTHESIS_DEFAULTS = {
    "culture_score": None,
    "salary_range": "",
    "interview_difficulty": "",
    "key_skills_extended": [],
    "red_flags": [],
    "recommendation": "insufficient_data",
    "summary": "",
}
GLASSDOOR_DEFAULTS = {
    "culture": "",
    "salary_range": "",
    "interview_difficulty": "",
    "summary": "",
}

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    chroma_client = chromadb.Client(ChromaSettings(anonymized_telemetry=False))
    jd_collection = chroma_client.get_or_create_collection(
        "jd_embeddings",
        configuration={"hnsw": {"space": "cosine"}},
    )
    company_collection = chroma_client.get_or_create_collection(
        "company_research",
        configuration={"hnsw": {"space": "cosine"}},
    )
except Exception as exc:
    logger.warning("Chroma initialization failed: %s", exc)
    chroma_client = None
    jd_collection = None
    company_collection = None


class BaseResearcher(ABC):
    source_name = "base"

    def __init__(self, agent: Any | None = None) -> None:
        self.agent = agent

    def bind(self, agent: Any) -> BaseResearcher:
        self.agent = agent
        return self

    def _require_agent(self) -> Any:
        if self.agent is None:
            raise RuntimeError(f"{self.__class__.__name__} is not bound to an agent")
        return self.agent

    @abstractmethod
    async def research(self, company: str, role: str) -> dict[str, Any]:
        raise NotImplementedError


class RedditResearcher(BaseResearcher):
    source_name = "reddit"

    async def research(self, company: str, role: str) -> dict[str, Any]:
        agent = self._require_agent()
        cache_key = make_cache_key("reddit", company, role)
        cached = await cache_get(cache_key)
        if isinstance(cached, dict):
            return cached

        query = f'site:reddit.com "{company}" "{role}" interview OR culture OR salary'
        results = await agent._serpapi_search(query, 5)
        snippets = agent._extract_snippets(results, limit=5)
        combined_snippets = "\n".join(f"- {snippet}" for snippet in snippets)

        summary = ""
        if combined_snippets:
            summary = await agent.llm.complete(
                prompt=(
                    "Summarize the following Reddit snippets about the company and role "
                    "in 3-4 factual sentences. Focus on interview experience, culture, "
                    "and salary signals. Do not invent details.\n\n"
                    f"Company: {company}\nRole: {role}\n\nSnippets:\n{combined_snippets}"
                ),
                system="You summarize public company discussion for recruiting research.",
                use_cache=False,
            )

        result = {
            "source": self.source_name,
            "query": query,
            "snippets": snippets,
            "summary": summary.strip(),
        }
        await cache_set(cache_key, result, ONE_DAY_CACHE_TTL_SECONDS)
        return result


class GlassdoorResearcher(BaseResearcher):
    source_name = "glassdoor"

    async def research(self, company: str, role: str) -> dict[str, Any]:
        agent = self._require_agent()
        cache_key = make_cache_key("glassdoor", company)
        cached = await cache_get(cache_key)
        if isinstance(cached, dict):
            return cached

        query = f'site:glassdoor.com "{company}" reviews OR salary OR interview'
        results = await agent._serpapi_search(query, 5)
        snippets = agent._extract_snippets(results, limit=5)
        combined_snippets = "\n".join(f"- {snippet}" for snippet in snippets)

        if not combined_snippets:
            result = {
                "source": self.source_name,
                "query": query,
                "snippets": snippets,
                **GLASSDOOR_DEFAULTS,
            }
            await cache_set(cache_key, result, ONE_DAY_CACHE_TTL_SECONDS)
            return result

        try:
            response = await agent.llm.complete(
                prompt=(
                    "Summarize the following Glassdoor snippets into JSON only.\n"
                    'Return {"culture": "", "salary_range": "", '
                    '"interview_difficulty": "", "summary": ""}.\n\n'
                    f"Company: {company}\nRole: {role}\n\nSnippets:\n{combined_snippets}"
                ),
                system="You extract factual company review signals and return JSON only.",
                use_cache=False,
            )
            parsed = agent._parse_json_object(response)
            normalized = agent._normalize_glassdoor_result(parsed)
        except Exception as exc:
            normalized = dict(GLASSDOOR_DEFAULTS)
            normalized["summary"] = " ".join(snippets).strip()
            normalized["error"] = str(exc)

        result = {
            "source": self.source_name,
            "query": query,
            "snippets": snippets,
            **normalized,
        }
        await cache_set(cache_key, result, ONE_DAY_CACHE_TTL_SECONDS)
        return result


class LinkedInResearcher(BaseResearcher):
    source_name = "linkedin"

    async def research(self, company: str, role: str) -> dict[str, Any]:
        agent = self._require_agent()
        query = f'site:linkedin.com/company "{company}"'
        results = await agent._serpapi_search(query, 5)
        snippets = agent._extract_snippets(results, limit=5)
        summary = " ".join(snippets).strip()
        return {
            "source": self.source_name,
            "query": query,
            "snippets": snippets,
            "summary": summary,
        }


class ResearcherFactory:
    _map: dict[str, type[BaseResearcher]] = {
        "reddit": RedditResearcher,
        "glassdoor": GlassdoorResearcher,
        "linkedin": LinkedInResearcher,
    }

    @classmethod
    def create(cls, source: str) -> BaseResearcher:
        researcher_cls = cls._map.get(source)
        if researcher_cls is None:
            raise ValueError(f"Unknown researcher source: {source}")
        return researcher_cls()


@AgentFactory.register("research")
class CompanyResearchAgent(BaseAgent):
    agent_name = "company_research"

    def validate_input(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        job_id = payload.get("job_id")
        company = payload.get("company_name") or payload.get("company")
        role = payload.get("role_title") or payload.get("role")
        return bool(job_id and company and role)

    async def process(self, payload: Any) -> dict[str, Any]:
        job_id = str(payload["job_id"])
        company = str(payload.get("company_name") or payload.get("company") or "")
        role = str(payload.get("role_title") or payload.get("role") or "")
        jd_text = str(payload.get("jd_text") or payload.get("raw_text") or "")

        researchers = [
            ResearcherFactory.create("reddit").bind(self),
            ResearcherFactory.create("glassdoor").bind(self),
            ResearcherFactory.create("linkedin").bind(self),
        ]
        results = await asyncio.gather(
            *(researcher.research(company, role) for researcher in researchers),
            return_exceptions=True,
        )

        research_results: dict[str, dict[str, Any]] = {}
        summaries: dict[str, str] = {}
        for researcher, result in zip(researchers, results, strict=True):
            source_name = researcher.source_name
            if isinstance(result, Exception):
                logger.error(
                    "Researcher %s failed: %s",
                    source_name,
                    result,
                    exc_info=result,
                )
                research_results[source_name] = {
                    "source": source_name,
                    "error": str(result),
                    "summary": "",
                }
                continue

            research_results[source_name] = result
            summary = str(result.get("summary") or "").strip()
            if summary:
                summaries[source_name] = summary

        synthesis = await self._synthesize(company, role, summaries, jd_text)
        all_summaries_text = self._join_summaries(summaries)
        embedding_text = self._build_embedding_text(jd_text, all_summaries_text)
        embedding_status = await self._store_embeddings(
            job_id,
            embedding_text,
            company,
            role,
            str(synthesis.get("summary") or ""),
        )

        glassdoor_result = research_results.get("glassdoor", {})
        enriched_payload = {
            "job_id": job_id,
            "company_name": company,
            "role_title": role,
            "jd_text": jd_text,
            "research_results": research_results,
            "reddit_summary": str(research_results.get("reddit", {}).get("summary") or ""),
            "glassdoor_summary": str(glassdoor_result.get("summary") or ""),
            "linkedin_summary": str(research_results.get("linkedin", {}).get("summary") or ""),
            "synthesis": synthesis,
            "required_skills_extended": synthesis.get("key_skills_extended", []),
            "salary_range": str(
                synthesis.get("salary_range")
                or glassdoor_result.get("salary_range")
                or ""
            ),
            "red_flags": synthesis.get("red_flags", []),
            "culture_notes": str(synthesis.get("summary") or ""),
            "interview_difficulty": str(synthesis.get("interview_difficulty") or ""),
            "recommendation": str(synthesis.get("recommendation") or ""),
            "embedding_status": embedding_status,
        }
        return enriched_payload

    async def emit_result(
        self,
        result: dict[str, Any],
        original_payload: Any,
    ) -> None:
        await queue_manager.publish(JD_ENRICHED, result, "jd.enriched.new")

    async def _serpapi_search(self, query: str, num: int) -> list[dict[str, Any]]:
        try:
            return await self._serpapi_search_with_retry(query, num)
        except Exception as exc:
            logger.exception("SerpAPI search failed for query %s: %s", query, exc)
            return []

    @with_exponential_backoff()
    async def _serpapi_search_with_retry(
        self,
        query: str,
        num: int,
    ) -> list[dict[str, Any]]:
        params = {
            "engine": "google",
            "q": query,
            "num": num,
            "api_key": settings.serpapi_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("https://serpapi.com/search", params=params)
            response.raise_for_status()
            payload = response.json()

        organic_results = payload.get("organic_results", [])
        if not isinstance(organic_results, list):
            return []
        return [result for result in organic_results if isinstance(result, dict)]

    async def _synthesize(
        self,
        company: str,
        role: str,
        summaries: dict[str, str],
        jd_text: str,
    ) -> dict[str, Any]:
        summary_block = self._join_summaries(summaries)
        prompt = (
            "Synthesize the following company research into JSON only.\n"
            'Return {"culture_score": null, "salary_range": "", '
            '"interview_difficulty": "", "key_skills_extended": [], '
            '"red_flags": [], "recommendation": "", "summary": ""}.\n\n'
            f"Company: {company}\nRole: {role}\n\n"
            f"Job description:\n{jd_text[:8000]}\n\n"
            f"Research summaries:\n{summary_block or 'No external summaries available.'}"
        )

        try:
            response = await self.llm.complete(
                prompt=prompt,
                system=(
                    "You are a recruiting research analyst. Synthesize factual company "
                    "signals and return JSON only."
                ),
                use_cache=False,
            )
            parsed = self._parse_json_object(response)
            return self._normalize_synthesis(parsed)
        except Exception as exc:
            fallback = dict(SYNTHESIS_DEFAULTS)
            fallback["summary"] = summary_block or ""
            fallback["synthesis_error"] = str(exc)
            return fallback

    async def _store_embeddings(
        self,
        job_id: str,
        embedding_text: str,
        company: str,
        role: str,
        synthesis_summary: str,
    ) -> dict[str, Any]:
        if jd_collection is None or company_collection is None:
            return {
                "jd_stored": False,
                "company_stored": False,
                "reason": "chroma_unavailable",
            }

        status = {
            "jd_stored": False,
            "company_stored": False,
        }

        try:
            jd_document = embedding_text[:2048]
            jd_embedding = await llm_client.embed(jd_document)
            jd_collection.upsert(
                ids=[job_id],
                embeddings=[jd_embedding],
                metadatas=[
                    {
                        "job_id": job_id,
                        "company": company,
                        "role": role,
                        "kind": "jd_research",
                    }
                ],
                documents=[jd_document],
            )
            status["jd_stored"] = True
        except Exception as exc:
            status["jd_error"] = str(exc)

        try:
            company_document = (
                f"Company: {company}\n"
                f"Role: {role}\n"
                f"Research summary:\n{synthesis_summary}\n\n"
                f"Context:\n{embedding_text[:2048]}"
            )[:2048]
            company_embedding = await llm_client.embed(company_document)
            company_collection.upsert(
                ids=[self._normalize_company_embedding_id(company, job_id)],
                embeddings=[company_embedding],
                metadatas=[
                    {
                        "job_id": job_id,
                        "company": company,
                        "role": role,
                        "kind": "company_research",
                    }
                ],
                documents=[company_document],
            )
            status["company_stored"] = True
        except Exception as exc:
            status["company_error"] = str(exc)

        return status

    @staticmethod
    def _extract_snippets(results: list[dict[str, Any]], limit: int = 5) -> list[str]:
        snippets: list[str] = []
        for result in results[:limit]:
            snippet = result.get("snippet")
            if isinstance(snippet, str) and snippet.strip():
                snippets.append(snippet.strip())
        return snippets

    @staticmethod
    def _parse_json_object(value: str) -> dict[str, Any]:
        stripped = value.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
        if fenced_match:
            stripped = fenced_match.group(1).strip()

        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("Expected JSON object response")
        return parsed

    @staticmethod
    def _normalize_glassdoor_result(data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(GLASSDOOR_DEFAULTS)
        normalized.update({key: data.get(key) for key in GLASSDOOR_DEFAULTS})
        for key in GLASSDOOR_DEFAULTS:
            normalized[key] = str(normalized.get(key) or "")
        return normalized

    @staticmethod
    def _normalize_synthesis(data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(SYNTHESIS_DEFAULTS)
        normalized.update({key: data.get(key) for key in SYNTHESIS_DEFAULTS})
        normalized["salary_range"] = str(normalized.get("salary_range") or "")
        normalized["interview_difficulty"] = str(
            normalized.get("interview_difficulty") or ""
        )
        normalized["recommendation"] = str(
            normalized.get("recommendation") or "insufficient_data"
        )
        normalized["summary"] = str(normalized.get("summary") or "")
        normalized["key_skills_extended"] = CompanyResearchAgent._normalize_string_list(
            normalized.get("key_skills_extended")
        )
        normalized["red_flags"] = CompanyResearchAgent._normalize_string_list(
            normalized.get("red_flags")
        )
        normalized["culture_score"] = CompanyResearchAgent._normalize_culture_score(
            normalized.get("culture_score")
        )
        return normalized

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        stripped = str(value).strip()
        return [stripped] if stripped else []

    @staticmethod
    def _normalize_culture_score(value: Any) -> int | float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value
        try:
            numeric = float(str(value).strip())
            return int(numeric) if numeric.is_integer() else numeric
        except ValueError:
            return None

    @staticmethod
    def _join_summaries(summaries: dict[str, str]) -> str:
        return "\n\n".join(
            f"{source}: {summary}" for source, summary in summaries.items() if summary
        )

    @staticmethod
    def _build_embedding_text(jd_text: str, all_summaries_text: str) -> str:
        if jd_text and all_summaries_text:
            return f"{jd_text}\n\n{all_summaries_text}"
        return jd_text or all_summaries_text

    @staticmethod
    def _normalize_company_embedding_id(company: str, job_id: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-") or "company"
        return f"{slug}:{job_id}"


__all__ = [
    "BaseResearcher",
    "CompanyResearchAgent",
    "GlassdoorResearcher",
    "LinkedInResearcher",
    "RedditResearcher",
    "ResearcherFactory",
    "chroma_client",
    "company_collection",
    "jd_collection",
]
