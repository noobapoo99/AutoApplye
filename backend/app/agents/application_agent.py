from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from playwright.async_api import Page
from playwright.async_api import async_playwright

from agents.base import AgentFactory
from agents.base import BaseAgent
from core.redis_client import acquire_lock
from core.redis_client import application_limiter
from core.redis_client import release_lock


logger = logging.getLogger(__name__)

APPLICATION_LOCK_TTL_SECONDS = 900
MAX_APPLY_ATTEMPTS = 4
PERSONAL_INFO_DELAY_SECONDS = 0.3
RESUME_UPLOAD_DELAY_SECONDS = 1.0
SUBMIT_WAIT_SECONDS = 3.0

GENERIC_NAME_SELECTORS = [
    'input[name="name"]',
    'input[name="full_name"]',
    'input[id="name"]',
    'input[id="full_name"]',
    'input[autocomplete="name"]',
]
EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name="email"]',
    'input[id="email"]',
    'input[autocomplete="email"]',
]
PHONE_SELECTORS = [
    'input[type="tel"]',
    'input[name="phone"]',
    'input[id="phone"]',
    'input[autocomplete="tel"]',
]
LINKEDIN_SELECTORS = [
    'input[name="linkedin"]',
    'input[id="linkedin"]',
    'input[name="linkedin_url"]',
    'input[id="linkedin_url"]',
    'input[placeholder*="linkedin" i]',
]
WORKDAY_FIRST_NAME_SELECTORS = [
    'input[data-automation-id="legalNameSection_firstName"]',
    'input[data-automation-id="firstName"]',
    'input[name="firstName"]',
]
WORKDAY_LAST_NAME_SELECTORS = [
    'input[data-automation-id="legalNameSection_lastName"]',
    'input[data-automation-id="lastName"]',
    'input[name="lastName"]',
]
GREENHOUSE_FIRST_NAME_SELECTORS = [
    "#first_name",
]
GREENHOUSE_LAST_NAME_SELECTORS = [
    "#last_name",
]
SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
]
CONFIRMATION_KEYWORDS = [
    "thank you",
    "application received",
    "submitted",
    "confirmation",
]


class BaseApplicationTemplate:
    ats_type = "generic"

    async def execute(
        self,
        page: Page,
        user_data: dict[str, Any],
        resume_path: str,
    ) -> dict[str, Any]:
        filled_fields = await self.fill_personal_info(page, user_data)
        resume_uploaded = await self.upload_resume(page, resume_path)
        custom_fields_filled = await self.fill_custom_fields(page, user_data)
        submitted = await self.submit(page)
        confirmation, confirmation_detected = await self.get_confirmation(page)

        return {
            "ats_type": self.ats_type,
            "filled_fields": self._dedupe_preserve_order(filled_fields),
            "resume_uploaded": resume_uploaded,
            "custom_fields_filled": self._dedupe_preserve_order(custom_fields_filled),
            "submitted": submitted,
            "confirmation": confirmation,
            "confirmation_detected": confirmation_detected,
            "final_url": page.url,
        }

    async def fill_personal_info(
        self,
        page: Page,
        user_data: dict[str, Any],
    ) -> list[str]:
        normalized_user_data = self._normalize_user_data(user_data)
        filled_fields: list[str] = []

        field_groups = [
            ("full_name", GENERIC_NAME_SELECTORS, normalized_user_data.get("full_name", "")),
            ("email", EMAIL_SELECTORS, normalized_user_data.get("email", "")),
            ("phone", PHONE_SELECTORS, normalized_user_data.get("phone", "")),
            ("linkedin", LINKEDIN_SELECTORS, normalized_user_data.get("linkedin", "")),
        ]

        for field_name, selectors, value in field_groups:
            if not value:
                continue
            if await self._fill_first_available(page, selectors, value):
                filled_fields.append(field_name)
                await asyncio.sleep(PERSONAL_INFO_DELAY_SECONDS)

        return filled_fields

    async def upload_resume(self, page: Page, resume_path: str) -> bool:
        file_input = await page.query_selector('input[type="file"]')
        if file_input is None:
            return False

        await file_input.set_input_files(resume_path)
        await asyncio.sleep(RESUME_UPLOAD_DELAY_SECONDS)
        return True

    async def fill_custom_fields(
        self,
        page: Page,
        user_data: dict[str, Any],
    ) -> list[str]:
        return []

    async def submit(self, page: Page) -> bool:
        for selector in SUBMIT_SELECTORS:
            button = await page.query_selector(selector)
            if button is None:
                continue

            try:
                await button.click()
                await asyncio.sleep(SUBMIT_WAIT_SECONDS)
                return True
            except Exception:
                logger.debug(
                    "Submit click failed for selector %s",
                    selector,
                    exc_info=True,
                )

        return False

    async def get_confirmation(self, page: Page) -> tuple[str, bool]:
        body = await page.query_selector("body")
        if body is None:
            return "No page body was available to confirm submission.", False

        try:
            page_text = (await body.inner_text()).strip()
        except Exception:
            logger.debug("Failed to read page text for confirmation", exc_info=True)
            return "Failed to read page text after submission.", False

        normalized_text = page_text.lower()
        matched_keywords = [
            keyword for keyword in CONFIRMATION_KEYWORDS if keyword in normalized_text
        ]
        if matched_keywords:
            joined_keywords = ", ".join(matched_keywords)
            return f"Detected confirmation keywords: {joined_keywords}.", True

        if page_text:
            return "No confirmation keywords detected in page text.", False
        return "Page text was empty after submission attempt.", False

    @staticmethod
    async def _fill_first_available(
        page: Page,
        selectors: list[str],
        value: str,
    ) -> bool:
        if not value:
            return False

        for selector in selectors:
            element = await page.query_selector(selector)
            if element is None:
                continue

            try:
                await element.fill(value)
                return True
            except Exception:
                logger.debug(
                    "Fill failed for selector %s",
                    selector,
                    exc_info=True,
                )

        return False

    @staticmethod
    def _normalize_user_data(user_data: dict[str, Any]) -> dict[str, str]:
        full_name = BaseApplicationTemplate._clean_value(user_data.get("full_name"))
        first_name = BaseApplicationTemplate._clean_value(user_data.get("first_name"))
        last_name = BaseApplicationTemplate._clean_value(user_data.get("last_name"))
        email = BaseApplicationTemplate._clean_value(user_data.get("email"))
        phone = BaseApplicationTemplate._clean_value(user_data.get("phone"))
        linkedin = BaseApplicationTemplate._clean_value(
            user_data.get("linkedin") or user_data.get("linkedin_url")
        )

        if full_name and (not first_name or not last_name):
            split_first_name, split_last_name = BaseApplicationTemplate._split_full_name(
                full_name
            )
            first_name = first_name or split_first_name
            last_name = last_name or split_last_name
        elif not full_name and (first_name or last_name):
            full_name = " ".join(part for part in [first_name, last_name] if part).strip()

        return {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "linkedin": linkedin,
        }

    @staticmethod
    def _split_full_name(full_name: str) -> tuple[str, str]:
        parts = full_name.split(maxsplit=1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        if len(parts) == 1:
            return parts[0].strip(), ""
        return "", ""

    @staticmethod
    def _clean_value(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _dedupe_preserve_order(values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped


class WorkdayTemplate(BaseApplicationTemplate):
    ats_type = "workday"

    async def fill_personal_info(
        self,
        page: Page,
        user_data: dict[str, Any],
    ) -> list[str]:
        normalized_user_data = self._normalize_user_data(user_data)
        filled_fields: list[str] = []

        if await self._fill_first_available(
            page,
            WORKDAY_FIRST_NAME_SELECTORS,
            normalized_user_data.get("first_name", ""),
        ):
            filled_fields.append("first_name")
            await asyncio.sleep(PERSONAL_INFO_DELAY_SECONDS)

        if await self._fill_first_available(
            page,
            WORKDAY_LAST_NAME_SELECTORS,
            normalized_user_data.get("last_name", ""),
        ):
            filled_fields.append("last_name")
            await asyncio.sleep(PERSONAL_INFO_DELAY_SECONDS)

        filled_fields.extend(await super().fill_personal_info(page, user_data))
        return self._dedupe_preserve_order(filled_fields)


class GreenhouseTemplate(BaseApplicationTemplate):
    ats_type = "greenhouse"

    async def fill_personal_info(
        self,
        page: Page,
        user_data: dict[str, Any],
    ) -> list[str]:
        normalized_user_data = self._normalize_user_data(user_data)
        filled_fields: list[str] = []

        if await self._fill_first_available(
            page,
            GREENHOUSE_FIRST_NAME_SELECTORS,
            normalized_user_data.get("first_name", ""),
        ):
            filled_fields.append("first_name")
            await asyncio.sleep(PERSONAL_INFO_DELAY_SECONDS)

        if await self._fill_first_available(
            page,
            GREENHOUSE_LAST_NAME_SELECTORS,
            normalized_user_data.get("last_name", ""),
        ):
            filled_fields.append("last_name")
            await asyncio.sleep(PERSONAL_INFO_DELAY_SECONDS)

        filled_fields.extend(await super().fill_personal_info(page, user_data))
        return self._dedupe_preserve_order(filled_fields)


def detect_ats(url: str) -> BaseApplicationTemplate:
    normalized_url = url.lower()
    if "myworkday" in normalized_url or "workday" in normalized_url:
        return WorkdayTemplate()
    if "greenhouse" in normalized_url:
        return GreenhouseTemplate()
    return BaseApplicationTemplate()


@AgentFactory.register("application")
class ApplicationAgent(BaseAgent):
    agent_name = "application"

    def __init__(
        self,
        user_data: dict[str, Any] | None = None,
        llm: Any | None = None,
        scorer: Any | None = None,
    ) -> None:
        super().__init__(llm=llm, scorer=scorer)
        if user_data:
            self.user_data = user_data
        else:
            # Load from persisted profile if available
            try:
                from core.resume_store import get_user_profile
                profile = get_user_profile()
                self.user_data = profile or {}
            except Exception:
                self.user_data = {}

    def validate_input(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        normalized = self._normalize_payload(payload)
        return bool(
            normalized["job_id"]
            and normalized["company_name"]
            and normalized["role_title"]
            and normalized["apply_url"]
            and normalized["resume_path"]
        )

    async def process(self, payload: Any) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        job_id = normalized["job_id"]
        company_name = normalized["company_name"]
        role_title = normalized["role_title"]
        apply_url = normalized["apply_url"]
        resume_path = normalized["resume_path"]
        match_score = normalized["match_score"]
        resume_version_id = normalized["resume_version_id"]

        lock_acquired = await acquire_lock(job_id, APPLICATION_LOCK_TTL_SECONDS)
        if not lock_acquired:
            return self._soft_failure_result(
                job_id=job_id,
                company_name=company_name,
                role_title=role_title,
                apply_url=apply_url,
                match_score=match_score,
                resume_version_id=resume_version_id,
                error="duplicate_in_progress",
            )

        try:
            allowed, wait_secs = await application_limiter.is_allowed()
            if not allowed:
                sleep_seconds = min(wait_secs, 60.0)
                await asyncio.sleep(sleep_seconds)
                allowed, wait_secs = await application_limiter.is_allowed()
                if not allowed:
                    return self._soft_failure_result(
                        job_id=job_id,
                        company_name=company_name,
                        role_title=role_title,
                        apply_url=apply_url,
                        match_score=match_score,
                        resume_version_id=resume_version_id,
                        error="rate_limited",
                        wait_seconds=sleep_seconds,
                    )

            form_fill_result = await self._apply_with_backoff(apply_url, resume_path)
            success = bool(
                form_fill_result.get("submitted")
                or form_fill_result.get("confirmation_detected")
            )

            return {
                "job_id": job_id,
                "company_name": company_name,
                "role_title": role_title,
                "apply_url": apply_url,
                "applied_at": (
                    datetime.now(timezone.utc).isoformat() if success else None
                ),
                "form_fill_result": form_fill_result,
                "success": success,
                "match_score": match_score,
                "resume_version_id": resume_version_id,
            }
        finally:
            await release_lock(job_id)

    async def _apply_with_backoff(
        self,
        url: str,
        resume_path: str,
    ) -> dict[str, Any]:
        last_exception: Exception | None = None

        for attempt in range(MAX_APPLY_ATTEMPTS):
            try:
                return await self._run_playwright(url, resume_path)
            except Exception as exc:
                last_exception = exc
                if attempt == MAX_APPLY_ATTEMPTS - 1:
                    break

                delay_seconds = (2**attempt) + (0.5 * attempt)
                logger.warning(
                    "Application attempt %s/%s failed for %s; retrying in %.2fs: %s",
                    attempt + 1,
                    MAX_APPLY_ATTEMPTS,
                    url,
                    delay_seconds,
                    exc,
                )
                await asyncio.sleep(delay_seconds)

        assert last_exception is not None
        raise last_exception

    async def _run_playwright(
        self,
        url: str,
        resume_path: str,
    ) -> dict[str, Any]:
        browser = None
        page = None

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle")
                template = detect_ats(url)
                return await template.execute(page, self.user_data, resume_path)
            finally:
                if page is not None:
                    try:
                        await page.close()
                    except Exception:
                        logger.debug("Failed to close application page", exc_info=True)
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:
                        logger.debug("Failed to close application browser", exc_info=True)

    async def emit_result(
        self,
        result: dict[str, Any],
        original_payload: Any,
    ) -> None:
        # Persist final application status to DB
        try:
            from db.models import ApplicationStatus
            from db.persistence import update_application_status
            from datetime import datetime, timezone

            job_id = result.get("job_id")
            success = bool(result.get("success"))
            if job_id:
                status = (
                    ApplicationStatus.applied if success else ApplicationStatus.applying
                )
                applied_at = None
                if success:
                    applied_at_raw = result.get("applied_at")
                    applied_at = (
                        datetime.fromisoformat(applied_at_raw)
                        if applied_at_raw else datetime.now(timezone.utc)
                    )
                await update_application_status(
                    job_id,
                    status,
                    applied_at=applied_at,
                    form_fill_result=result.get("form_fill_result"),
                )
        except Exception as exc:
            logger.exception("Failed to persist application status to DB: %s", exc)

        logger.info(
            "Application agent completed for job_id=%s success=%s error=%s",
            result.get("job_id"),
            result.get("success"),
            result.get("error"),
        )

    @staticmethod
    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": str(payload.get("job_id") or "").strip(),
            "company_name": str(
                payload.get("company_name") or payload.get("company") or ""
            ).strip(),
            "role_title": str(
                payload.get("role_title") or payload.get("role") or ""
            ).strip(),
            "apply_url": str(
                payload.get("apply_url") or payload.get("external_apply_url") or ""
            ).strip(),
            "resume_path": str(
                payload.get("resume_path") or payload.get("edited_resume_path") or ""
            ).strip(),
            "match_score": ApplicationAgent._normalize_match_score(
                payload.get("match_score", payload.get("match_score_after"))
            ),
            "resume_version_id": ApplicationAgent._normalize_optional_string(
                payload.get("resume_version_id")
            ),
        }

    @staticmethod
    def _normalize_match_score(value: Any) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except ValueError:
            return None

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if value in (None, ""):
            return None
        normalized = str(value).strip()
        return normalized or None

    @staticmethod
    def _soft_failure_result(
        *,
        job_id: str,
        company_name: str,
        role_title: str,
        apply_url: str,
        match_score: float | None,
        resume_version_id: str | None,
        error: str,
        wait_seconds: float | None = None,
    ) -> dict[str, Any]:
        result = {
            "job_id": job_id,
            "company_name": company_name,
            "role_title": role_title,
            "apply_url": apply_url,
            "applied_at": None,
            "form_fill_result": None,
            "success": False,
            "match_score": match_score,
            "resume_version_id": resume_version_id,
            "error": error,
        }
        if wait_seconds is not None:
            result["wait_seconds"] = wait_seconds
        return result


__all__ = [
    "ApplicationAgent",
    "BaseApplicationTemplate",
    "GreenhouseTemplate",
    "WorkdayTemplate",
    "detect_ats",
]
