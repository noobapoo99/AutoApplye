from datetime import datetime, timezone
from typing import Any

from db.models import Application
from db.models import EmailThread
from db.models import ApplicationStatus


def serialize_application_summary(application: Application) -> dict[str, Any]:
    return {
        "id": application.id,
        "job_id": application.job_id,
        "company_name": application.company_name,
        "role_title": application.role_title,
        "status": application.status.value,
        "match_score": application.match_score,
        "applied_at": serialize_datetime(application.applied_at),
        "last_updated": serialize_datetime(application.last_updated),
    }


def serialize_application_detail(application: Application) -> dict[str, Any]:
    email_threads = sorted(
        application.email_threads,
        key=lambda thread: thread.received_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return {
        "id": application.id,
        "job_id": application.job_id,
        "company_name": application.company_name,
        "role_title": application.role_title,
        "status": application.status.value,
        "match_score": application.match_score,
        "applied_at": serialize_datetime(application.applied_at),
        "last_updated": serialize_datetime(application.last_updated),
        "resume_version_id": application.resume_version_id,
        "flagged_reason": application.flagged_reason,
        "hallucination_score": application.hallucination_score,
        "notes": application.notes,
        "form_fill_result": application.form_fill_result,
        "email_threads": [serialize_email_thread(thread) for thread in email_threads],
    }


def serialize_email_thread(thread: EmailThread) -> dict[str, Any]:
    return {
        "id": thread.id,
        "application_id": thread.application_id,
        "gmail_thread_id": thread.gmail_thread_id,
        "subject": thread.subject,
        "sender": thread.sender,
        "classification": thread.classification,
        "ai_summary": thread.ai_summary,
        "draft_followup": thread.draft_followup,
        "received_at": serialize_datetime(thread.received_at),
        "dlq_attempts": thread.dlq_attempts,
    }


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def serialize_status(value: ApplicationStatus | str | None) -> str:
    if isinstance(value, ApplicationStatus):
        return value.value
    return str(value or "")
