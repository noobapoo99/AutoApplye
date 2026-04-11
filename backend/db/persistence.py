"""
persistence.py — Async helper functions to persist agent pipeline results to Postgres.

Each function is idempotent (upsert-style) so agents can call them safely on retry.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import (
    Application,
    ApplicationStatus,
    AsyncSessionLocal,
    CompanyResearch,
    Job,
    ResumeVersion,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

async def upsert_job(payload: dict[str, Any]) -> str:
    """
    Insert or update a Job row from a scout agent payload.
    Also creates a stub Application row so the dashboard shows the job immediately.
    Returns the job_id string.
    """
    from uuid import uuid4

    job_id: str = str(payload["job_id"])
    source_url: str = str(payload.get("source_url") or "")
    company_name: str = str(payload.get("company_name") or "Unknown Company")
    role_title: str = str(payload.get("role_title") or "Unknown Role")
    raw_text: str = str(payload.get("raw_text") or "")
    screenshot_path: str | None = payload.get("screenshot_path")
    external_apply_url: str | None = payload.get("external_apply_url")

    async with AsyncSessionLocal() as session:
        existing_job = await session.get(Job, job_id)
        if existing_job is None:
            job = Job(
                id=job_id,
                source_url=source_url,
                company_name=_truncate(company_name),
                role_title=_truncate(role_title),
                raw_text=raw_text[:50000],
                screenshot_path=screenshot_path,
                external_apply_url=external_apply_url,
                raw_payload=_safe_payload(payload),
                status=ApplicationStatus.discovered,
            )
            session.add(job)
            logger.info("Inserting new Job row: job_id=%s company=%s", job_id, company_name)
        else:
            # Update mutable fields in case of re-scrape
            existing_job.raw_text = raw_text[:50000]
            existing_job.screenshot_path = screenshot_path or existing_job.screenshot_path
            existing_job.external_apply_url = external_apply_url or existing_job.external_apply_url
            existing_job.raw_payload = _safe_payload(payload)
            logger.debug("Updated existing Job row: job_id=%s", job_id)

        # Also create a stub Application so the dashboard shows this job immediately
        existing_app = await session.scalar(
            select(Application).where(Application.job_id == job_id)
        )
        if existing_app is None:
            app = Application(
                id=str(uuid4()),
                job_id=job_id,
                company_name=_truncate(company_name),
                role_title=_truncate(role_title),
                status=ApplicationStatus.discovered,
                hallucination_score=_safe_hallucination_score(payload),
            )
            session.add(app)
            logger.info(
                "Inserting stub Application for job_id=%s company=%s",
                job_id, company_name,
            )

        await session.commit()
    return job_id


# ---------------------------------------------------------------------------
# CompanyResearch
# ---------------------------------------------------------------------------

async def upsert_research(payload: dict[str, Any]) -> str:
    """
    Insert or update a CompanyResearch row from a research agent payload.
    Returns the research record id.
    """
    job_id: str = str(payload["job_id"])
    company_name: str = str(payload.get("company_name") or "")

    from uuid import uuid4
    research_id = str(uuid4())

    async with AsyncSessionLocal() as session:
        # Ensure the parent Job exists first
        job = await session.get(Job, job_id)
        if job is None:
            logger.warning("upsert_research: No Job found for job_id=%s — skipping", job_id)
            return ""

        # Update job status
        job.status = ApplicationStatus.researching

        existing_research = await session.scalar(
            select(CompanyResearch).where(CompanyResearch.job_id == job_id)
        )
        if existing_research is None:
            research = CompanyResearch(
                id=research_id,
                job_id=job_id,
                company_name=_truncate(company_name),
                reddit_summary=str(payload.get("reddit_summary") or "")[:10000],
                glassdoor_summary=str(payload.get("glassdoor_summary") or "")[:10000],
                culture_notes=str(payload.get("culture_notes") or "")[:10000],
                required_skills_extended=payload.get("required_skills_extended") or [],
                salary_range=_truncate(str(payload.get("salary_range") or "")),
                red_flags=payload.get("red_flags") or [],
                hallucination_score=_safe_hallucination_score(payload),
            )
            session.add(research)
            logger.info("Inserting CompanyResearch for job_id=%s", job_id)
        else:
            existing_research.reddit_summary = str(payload.get("reddit_summary") or "")[:10000]
            existing_research.glassdoor_summary = str(payload.get("glassdoor_summary") or "")[:10000]
            existing_research.culture_notes = str(payload.get("culture_notes") or "")[:10000]
            existing_research.required_skills_extended = payload.get("required_skills_extended") or []
            existing_research.salary_range = str(payload.get("salary_range") or "")[:255]
            existing_research.red_flags = payload.get("red_flags") or []
            existing_research.hallucination_score = _safe_hallucination_score(payload)
            research_id = existing_research.id
            logger.debug("Updated CompanyResearch for job_id=%s", job_id)

        await session.commit()
    return research_id


# ---------------------------------------------------------------------------
# ResumeVersion
# ---------------------------------------------------------------------------

async def upsert_resume_version(payload: dict[str, Any]) -> str:
    """
    Insert a ResumeVersion row from a resume agent payload.
    Returns the resume_version_id string.
    """
    from uuid import uuid4

    job_id: str = str(payload["job_id"])
    resume_version_id = str(uuid4())

    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        if job is None:
            logger.warning("upsert_resume_version: No Job for job_id=%s — skipping", job_id)
            return ""

        job.status = ApplicationStatus.resume_editing

        resume_version = ResumeVersion(
            id=resume_version_id,
            job_id=job_id,
            original_filename=str(payload.get("original_filename") or "base_resume.docx"),
            edited_filename=str(payload.get("edited_filename") or f"{job_id}_edited.docx"),
            changes_made=payload.get("changes_made") or [],
            match_score_before=_safe_float(payload.get("match_score_before")),
            match_score_after=_safe_float(payload.get("match_score_after")),
        )
        session.add(resume_version)
        logger.info("Inserting ResumeVersion for job_id=%s", job_id)
        await session.commit()

    return resume_version_id


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

async def upsert_application(
    payload: dict[str, Any],
    resume_version_id: str | None = None,
) -> str:
    """
    Insert or update an Application row. This is the record the frontend reads.
    Returns the application id.
    """
    from uuid import uuid4

    job_id: str = str(payload["job_id"])
    company_name: str = str(payload.get("company_name") or "Unknown Company")
    role_title: str = str(payload.get("role_title") or "Unknown Role")
    match_score = _safe_float(
        payload.get("match_score_after") or payload.get("match_score")
    )
    needs_review: bool = bool(payload.get("needs_human_review", False))
    flag_reason: str | None = payload.get("flag_reason")
    hallucination_score = _safe_hallucination_score(payload)

    status = (
        ApplicationStatus.flagged_human
        if needs_review
        else ApplicationStatus.resume_editing
    )

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(Application).where(Application.job_id == job_id)
        )
        if existing is None:
            app_id = str(uuid4())
            application = Application(
                id=app_id,
                job_id=job_id,
                company_name=_truncate(company_name),
                role_title=_truncate(role_title),
                status=status,
                resume_version_id=resume_version_id,
                match_score=match_score,
                flagged_reason=flag_reason,
                hallucination_score=hallucination_score,
            )
            session.add(application)
            logger.info(
                "Inserting Application for job_id=%s company=%s status=%s",
                job_id, company_name, status.value,
            )
        else:
            app_id = existing.id
            # Only update if we're at a later stage; don't regress status
            if _should_update_status(existing.status, status):
                existing.status = status
            if match_score is not None:
                existing.match_score = match_score
            if resume_version_id:
                existing.resume_version_id = resume_version_id
            if flag_reason:
                existing.flagged_reason = flag_reason
            existing.hallucination_score = hallucination_score
            logger.debug("Updated Application for job_id=%s", job_id)

        await session.commit()
    return app_id


# ---------------------------------------------------------------------------
# Status update (used by application agent on submit)
# ---------------------------------------------------------------------------

async def update_application_status(
    job_id: str,
    status: ApplicationStatus,
    applied_at: datetime | None = None,
    form_fill_result: dict[str, Any] | None = None,
) -> None:
    """Update an Application's status after the application agent runs."""
    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(Application).where(Application.job_id == job_id)
        )
        if application is None:
            logger.warning(
                "update_application_status: No Application found for job_id=%s", job_id
            )
            return

        application.status = status
        if applied_at is not None:
            application.applied_at = applied_at
        if form_fill_result is not None:
            application.form_fill_result = form_fill_result

        # Also update parent Job row
        job = await session.get(Job, job_id)
        if job:
            job.status = status

        await session.commit()
        logger.info("Updated Application status job_id=%s → %s", job_id, status.value)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_ORDER = [
    ApplicationStatus.discovered,
    ApplicationStatus.researching,
    ApplicationStatus.resume_editing,
    ApplicationStatus.flagged_human,
    ApplicationStatus.applying,
    ApplicationStatus.applied,
    ApplicationStatus.email_received,
    ApplicationStatus.interview,
    ApplicationStatus.rejected,
    ApplicationStatus.withdrawn,
]


def _should_update_status(
    current: ApplicationStatus,
    new: ApplicationStatus,
) -> bool:
    """Only advance the status, never regress it."""
    try:
        return _STATUS_ORDER.index(new) > _STATUS_ORDER.index(current)
    except ValueError:
        return True


def _truncate(value: Any, limit: int = 255) -> str:
    """Safely cast to string and truncate to limit."""
    if value is None:
        return ""
    text = str(value)
    return text[:limit] if len(text) > limit else text


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_hallucination_score(payload: dict[str, Any]) -> int:
    """Extract hallucination score from payload, clamped to 0–6."""
    hc = payload.get("hallucination_check") or {}
    raw = hc.get("score") if isinstance(hc, dict) else 0
    try:
        score = int(raw or 0)
        return max(0, min(6, score))
    except (TypeError, ValueError):
        return 0


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of payload with very large string values trimmed."""
    safe: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str) and len(v) > 5000:
            safe[k] = v[:5000]
        elif isinstance(v, (dict, list, int, float, bool, type(None))):
            safe[k] = v
        else:
            safe[k] = str(v)[:5000]
    return safe


__all__ = [
    "upsert_job",
    "upsert_research",
    "upsert_resume_version",
    "upsert_application",
    "update_application_status",
]
