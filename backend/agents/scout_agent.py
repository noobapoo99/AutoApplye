from __future__ import annotations

import asyncio
import base64
from pathlib import Path
import json
import logging
import re
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from PIL import Image
from playwright.async_api import Page
from playwright.async_api import async_playwright
import pytesseract

from agents.base import AgentFactory
from agents.base import BaseAgent
from core.config import get_settings
from core.llm import with_exponential_backoff
from core.queue import JD_RAW
from core.queue import queue_manager
from core.redis_client import cache_get
from core.redis_client import cache_set
from core.redis_client import make_cache_key


logger = logging.getLogger(__name__)
settings = get_settings()
SCREENSHOT_DIR = Path("/tmp/screenshots")
SERPAPI_CACHE_TTL_SECONDS = 3600
STRUCTURED_SCHEMA_DEFAULTS = {
    "company_name": "",
    "role_title": "",
    "location": "",
    "required_skills": [],
    "nice_to_have_skills": [],
    "experience_years": None,
    "salary_range": "",
    "job_type": "",
    "summary": "",
}


@AgentFactory.register("scout")
class JDScoutAgent(BaseAgent):
    agent_name = "jd_scout"

    def __init__(
        self,
        search_query: str | None = None,
        max_jobs: int = 5,
        llm: Any | None = None,
        scorer: Any | None = None,
    ) -> None:
        super().__init__(llm=llm, scorer=scorer)
        self.search_query = search_query
        self.max_jobs = max_jobs

    def validate_input(self, payload: Any) -> bool:
        if isinstance(payload, dict) and payload.get("search_query"):
            return True
        return bool(self.search_query)

    async def process(self, payload: Any) -> dict[str, Any]:
        query = self._resolve_query(payload)
        urls = await self._search_jobs(query)
        total_found = len(urls)

        discovered_jobs: list[dict[str, Any]] = []
        for url in urls[: self.max_jobs]:
            job = await self._scrape_job(url)
            if job is not None:
                discovered_jobs.append(job)

        return {
            "discovered_jobs": discovered_jobs,
            "query": query,
            "total_found": total_found,
        }

    async def emit_result(
        self,
        result: dict[str, Any],
        original_payload: Any,
    ) -> None:
        from db.persistence import upsert_job
        for job_payload in result.get("discovered_jobs", []):
            # Persist job to DB first so it appears on frontend
            try:
                await upsert_job(job_payload)
            except Exception as exc:
                logger.exception("Failed to persist job %s to DB: %s", job_payload.get("job_id"), exc)
            # Then publish to research queue
            await queue_manager.publish(JD_RAW, job_payload, "jd.raw.new")

    @with_exponential_backoff()
    async def _search_jobs(self, query: str) -> list[str]:
        cache_key = make_cache_key("serpapi", query)
        cached = await cache_get(cache_key)
        if isinstance(cached, list):
            return [str(url) for url in cached]

        params = {
            "engine": "google",
            "q": f'site:linkedin.com/jobs "{query}"',
            "api_key": settings.serpapi_key,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("https://serpapi.com/search.json", params=params)
            response.raise_for_status()
            payload = response.json()

        urls = self._extract_linkedin_urls(payload)
        await cache_set(cache_key, urls, SERPAPI_CACHE_TTL_SECONDS)
        return urls

    async def _scrape_job(self, url: str) -> dict[str, Any] | None:
        browser = None
        page = None
        screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"

        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await page.screenshot(path=str(screenshot_path), full_page=True)
                dom_text = await page.evaluate("document.body.innerText")
                external_apply_url = await self._find_apply_url(page)
        except Exception:
            logger.exception("Failed to scrape job from %s", url)
            return None
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    logger.debug("Failed to close page for %s", url, exc_info=True)
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    logger.debug("Failed to close browser for %s", url, exc_info=True)

        try:
            ocr_text = await asyncio.to_thread(self._ocr_screenshot, screenshot_path)
            combined_text = self._combine_text(dom_text, ocr_text)
            structured = await self._extract_structured(combined_text, url)

            structured_error = structured.pop("structured_extraction_error", None)
            result = {
                "job_id": str(uuid4()),
                "source_url": url,
                "raw_text": combined_text[:5000],
                "screenshot_path": str(screenshot_path),
                "screenshot_b64": self._img_to_b64(screenshot_path),
                "external_apply_url": external_apply_url,
                **structured,
            }
            if structured_error:
                result["structured_extraction_error"] = structured_error
            return result
        except Exception:
            logger.exception("Failed post-processing scraped job from %s", url)
            return None

    async def _find_apply_url(self, page: Page) -> str | None:
        anchors = await page.eval_on_selector_all(
            "a[href]",
            """
            (elements) => elements.map((element) => ({
                href: element.getAttribute('href') || '',
                text: (element.innerText || '').trim(),
                ariaLabel: (element.getAttribute('aria-label') || '').trim(),
            }))
            """,
        )

        candidates: list[tuple[int, str]] = []
        for anchor in anchors:
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue

            haystack = " ".join(
                [
                    str(anchor.get("text") or ""),
                    str(anchor.get("ariaLabel") or ""),
                    href,
                ]
            ).lower()

            score = 0
            if "easy apply" in haystack:
                score += 3
            if "apply" in haystack:
                score += 2
            if "application" in haystack:
                score += 1

            if score > 0:
                candidates.append((score, urljoin(page.url, href)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    async def _extract_structured(self, text: str, url: str) -> dict[str, Any]:
        system = (
            "You extract factual job posting metadata. Use only the supplied job text, "
            "do not invent missing details, and return JSON only."
        )
        prompt = (
            "Extract structured information from the following job posting text.\n\n"
            f"Source URL: {url}\n\n"
            "Return a JSON object with exactly these keys:\n"
            "{"
            '"company_name": "", '
            '"role_title": "", '
            '"location": "", '
            '"required_skills": [], '
            '"nice_to_have_skills": [], '
            '"experience_years": null, '
            '"salary_range": "", '
            '"job_type": "", '
            '"summary": ""'
            "}\n\n"
            "Job text:\n"
            f"{text[:5000]}"
        )

        try:
            response = await self.llm.complete(
                prompt=prompt,
                system=system,
                use_cache=False,
            )
            normalized_text = self._strip_markdown_fences(response)
            parsed = json.loads(normalized_text)
            if not isinstance(parsed, dict):
                raise ValueError("Structured extraction response was not a JSON object")
            return self._normalize_structured(parsed)
        except Exception as exc:
            fallback = self._empty_structured_payload()
            fallback["summary"] = self._clean_summary_fallback(text)
            fallback["structured_extraction_error"] = str(exc)
            return fallback

    @staticmethod
    def _img_to_b64(path: str | Path) -> str:
        image_bytes = Path(path).read_bytes()
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def _extract_linkedin_urls(payload: dict[str, Any]) -> list[str]:
        organic_results = payload.get("organic_results", [])
        seen: set[str] = set()
        urls: list[str] = []

        for item in organic_results:
            if not isinstance(item, dict):
                continue
            link = item.get("link")
            if not isinstance(link, str):
                continue
            if "linkedin.com/jobs" not in link:
                continue
            if link in seen:
                continue
            seen.add(link)
            urls.append(link)

        return urls

    @staticmethod
    def _strip_markdown_fences(value: str) -> str:
        stripped = value.strip()
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
        if fenced_match:
            return fenced_match.group(1).strip()
        return stripped

    @staticmethod
    def _normalize_structured(data: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(STRUCTURED_SCHEMA_DEFAULTS)
        normalized.update({key: data.get(key) for key in STRUCTURED_SCHEMA_DEFAULTS})

        normalized["company_name"] = str(normalized.get("company_name") or "Unknown Company")
        normalized["role_title"] = str(normalized.get("role_title") or "Unknown Role")
        normalized["location"] = str(normalized.get("location") or "")
        normalized["salary_range"] = str(normalized.get("salary_range") or "")
        normalized["job_type"] = str(normalized.get("job_type") or "")
        normalized["summary"] = str(normalized.get("summary") or "")
        normalized["required_skills"] = JDScoutAgent._normalize_string_list(
            normalized.get("required_skills")
        )
        normalized["nice_to_have_skills"] = JDScoutAgent._normalize_string_list(
            normalized.get("nice_to_have_skills")
        )
        normalized["experience_years"] = JDScoutAgent._normalize_experience_years(
            normalized.get("experience_years")
        )
        return normalized

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None:
            return []
        string_value = str(value).strip()
        return [string_value] if string_value else []

    @staticmethod
    def _normalize_experience_years(value: Any) -> int | float | str | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return value
        stripped = str(value).strip()
        if not stripped:
            return None
        try:
            numeric = float(stripped)
            return int(numeric) if numeric.is_integer() else numeric
        except ValueError:
            return stripped

    @staticmethod
    def _empty_structured_payload() -> dict[str, Any]:
        return {
            "company_name": "",
            "role_title": "",
            "location": "",
            "required_skills": [],
            "nice_to_have_skills": [],
            "experience_years": None,
            "salary_range": "",
            "job_type": "",
            "summary": "",
        }

    @staticmethod
    def _clean_summary_fallback(text: str) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:500]

    @staticmethod
    def _combine_text(dom_text: str, ocr_text: str) -> str:
        return f"{dom_text.strip()}\n\n--- OCR ---\n\n{ocr_text.strip()}".strip()

    @staticmethod
    def _ocr_screenshot(path: Path) -> str:
        with Image.open(path) as image:
            processed = image
            if image.width > 1920:
                ratio = 1920 / image.width
                new_height = max(1, int(image.height * ratio))
                processed = image.resize((1920, new_height))
            return pytesseract.image_to_string(processed)

    def _resolve_query(self, payload: Any) -> str:
        if isinstance(payload, dict) and payload.get("search_query"):
            return str(payload["search_query"])
        if self.search_query:
            return self.search_query
        raise ValueError("search_query is required")


__all__ = ["JDScoutAgent"]
