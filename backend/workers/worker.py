from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agents import application_agent as _application_agent  # noqa: F401
from agents import gmail_agent as _gmail_agent  # noqa: F401
from agents import research_agent as _research_agent  # noqa: F401
from agents import resume_agent as _resume_agent  # noqa: F401
from agents.base import AgentFactory
from core.queue import JD_ENRICHED
from core.queue import JD_RAW
from core.queue import JD_READY
from core.queue import queue_manager
from db.models import Application
from db.models import ApplicationStatus
from db.models import AsyncSessionLocal
from db.models import EmailThread


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

APPLICATION_USER_DATA_ENV = "APPLICATION_USER_DATA_JSON"
GMAIL_CREDENTIALS_ENV = "GMAIL_OAUTH_CREDENTIALS_JSON"
GMAIL_POLL_INTERVAL_SECONDS = 1800
GMAIL_ACTIVE_STATUSES = (
    ApplicationStatus.applied,
    ApplicationStatus.email_received,
    ApplicationStatus.interview,
)
QUEUE_WORKERS: dict[str, tuple[str, str]] = {
    "scout": ("research", JD_RAW),
    "research": ("research", JD_RAW),
    "resume": ("resume", JD_ENRICHED),
    "application": ("application", JD_READY),
}
SUPPORTED_WORKER_TYPES = set(QUEUE_WORKERS) | {"gmail"}
VALID_EMAIL_CLASSIFICATIONS = {
    "interview_invite",
    "rejection",
    "assessment",
    "follow_up_needed",
    "other",
}


async def run_worker() -> None:
    worker_type = os.environ.get("WORKER_TYPE", "").strip().lower()
    if worker_type not in SUPPORTED_WORKER_TYPES:
        supported = ", ".join(sorted(SUPPORTED_WORKER_TYPES))
        raise ValueError(
            f"Unsupported WORKER_TYPE '{worker_type}'. Expected one of: {supported}"
        )

    await queue_manager.connect()

    try:
        if worker_type == "gmail":
            await _run_gmail_worker()
            return

        await _run_queue_worker(worker_type)
    finally:
        await queue_manager.close()


async def _run_queue_worker(worker_type: str) -> None:
    agent_type, queue_name = QUEUE_WORKERS[worker_type]
    agent_kwargs: dict[str, Any] = {}

    if worker_type == "application":
        agent_kwargs["user_data"] = _load_json_env(
            APPLICATION_USER_DATA_ENV,
            required=True,
        )

    agent = AgentFactory.create(agent_type, **agent_kwargs)

    async def handle(payload: dict[str, Any]) -> None:
        await agent.run(payload)

    await queue_manager.consume(queue_name, handle)
    logger.info(
        "Worker type=%s consuming queue=%s with agent=%s",
        worker_type,
        queue_name,
        agent_type,
    )

    await asyncio.Event().wait()


async def _run_gmail_worker() -> None:
    credentials = _load_json_env(GMAIL_CREDENTIALS_ENV, required=False)
    if credentials is None:
        logger.warning(
            "%s is not set; Gmail worker will poll as a no-op.",
            GMAIL_CREDENTIALS_ENV,
        )

    while True:
        if credentials is not None:
            await _poll_gmail_once(credentials)
        else:
            logger.info("Skipping Gmail poll cycle because credentials are unavailable.")
        await asyncio.sleep(GMAIL_POLL_INTERVAL_SECONDS)


async def _poll_gmail_once(credentials: dict[str, Any]) -> None:
    agent = AgentFactory.create("gmail", credentials=credentials)

    async with AsyncSessionLocal() as session:
        applications = (
            await session.scalars(
                select(Application).where(
                    Application.status.in_(GMAIL_ACTIVE_STATUSES),
                    Application.applied_at.is_not(None),
                )
            )
        ).all()

        logger.info("Gmail worker polling %s applications", len(applications))

        for application in applications:
            try:
                result = await agent.run(
                    {
                        "application_id": application.id,
                        "company_name": application.company_name,
                        "role_title": application.role_title,
                        "applied_at": application.applied_at.isoformat(),
                    }
                )
                await _persist_gmail_result(session, application, result)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Gmail worker failed for application_id=%s",
                    application.id,
                )


async def _persist_gmail_result(
    session: Any,
    application: Application,
    result: dict[str, Any],
) -> None:
    thread_payloads = result.get("email_threads", [])
    if not isinstance(thread_payloads, list):
        thread_payloads = []

    thread_ids = [
        str(thread.get("gmail_thread_id") or "").strip()
        for thread in thread_payloads
        if isinstance(thread, dict) and str(thread.get("gmail_thread_id") or "").strip()
    ]

    existing_by_thread: dict[str, EmailThread] = {}
    if thread_ids:
        existing_threads = (
            await session.scalars(
                select(EmailThread).where(
                    EmailThread.application_id == application.id,
                    EmailThread.gmail_thread_id.in_(thread_ids),
                )
            )
        ).all()
        existing_by_thread = {
            existing.gmail_thread_id: existing for existing in existing_threads
        }

    for thread_payload in thread_payloads:
        if not isinstance(thread_payload, dict):
            continue

        gmail_thread_id = str(thread_payload.get("gmail_thread_id") or "").strip()
        if not gmail_thread_id:
            continue

        subject = str(thread_payload.get("subject") or "").strip() or "(no subject)"
        sender = str(thread_payload.get("sender") or "").strip() or "unknown"
        classification = _normalize_classification(thread_payload.get("classification"))
        received_at = _parse_datetime(thread_payload.get("received_at"))
        ai_summary = _normalize_optional_text(thread_payload.get("ai_summary"))
        draft_followup = _normalize_optional_text(thread_payload.get("draft_followup"))
        dlq_attempts = _normalize_dlq_attempts(thread_payload.get("dlq_attempts"))

        existing = existing_by_thread.get(gmail_thread_id)
        if existing is None:
            session.add(
                EmailThread(
                    application_id=application.id,
                    gmail_thread_id=gmail_thread_id,
                    subject=subject,
                    sender=sender,
                    classification=classification,
                    ai_summary=ai_summary,
                    draft_followup=draft_followup,
                    received_at=received_at,
                    dlq_attempts=dlq_attempts,
                )
            )
            continue

        existing.subject = subject
        existing.sender = sender
        existing.classification = classification
        existing.ai_summary = ai_summary
        existing.draft_followup = draft_followup
        existing.received_at = received_at
        existing.dlq_attempts = dlq_attempts

    _update_application_status(application, thread_payloads)


def _update_application_status(
    application: Application,
    thread_payloads: list[dict[str, Any]],
) -> None:
    classifications = {
        _normalize_classification(thread.get("classification"))
        for thread in thread_payloads
        if isinstance(thread, dict)
    }

    if "rejection" in classifications:
        application.status = ApplicationStatus.rejected
        return

    if "interview_invite" in classifications:
        application.status = ApplicationStatus.interview
        return

    if classifications and application.status == ApplicationStatus.applied:
        application.status = ApplicationStatus.email_received


def _load_json_env(name: str, required: bool) -> dict[str, Any] | None:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        if required:
            raise ValueError(f"Missing required environment variable: {name}")
        return None

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Environment variable {name} must contain valid JSON") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Environment variable {name} must decode to a JSON object")

    return parsed


def _normalize_classification(value: Any) -> str:
    normalized = str(value or "other").strip().lower()
    if normalized not in VALID_EMAIL_CLASSIFICATIONS:
        return "other"
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_dlq_attempts(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
