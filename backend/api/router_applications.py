from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.serializers import (
    serialize_application_summary,
    serialize_application_detail,
    serialize_datetime,
)
from db.models import Application, ApplicationStatus, AsyncSessionLocal

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/applications")
async def list_applications() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        applications = (
            await session.scalars(
                select(Application).order_by(Application.last_updated.desc())
            )
        ).all()
        return [serialize_application_summary(application) for application in applications]


@router.get("/applications/{application_id}")
async def get_application(application_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(Application)
            .options(selectinload(Application.email_threads))
            .where(Application.id == application_id)
        )
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")

        return serialize_application_detail(application)


@router.get("/flagged")
async def get_flagged_applications() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        applications = (
            await session.scalars(
                select(Application)
                .where(Application.status == ApplicationStatus.flagged_human)
                .order_by(Application.last_updated.desc())
            )
        ).all()

        return [
            {
                "id": application.id,
                "job_id": application.job_id,
                "company_name": application.company_name,
                "role_title": application.role_title,
                "status": application.status.value,
                "match_score": application.match_score,
                "flagged_reason": application.flagged_reason,
                "hallucination_score": application.hallucination_score,
                "last_updated": serialize_datetime(application.last_updated),
            }
            for application in applications
        ]


@router.get("/emails")
async def list_emails() -> list[dict[str, Any]]:
    # This was also in main.py, let's keep it in applications router for now as it relates to communications
    # from core.serializers import serialize_email_thread
    from api.serializers import serialize_email_thread
    from db.models import EmailThread
    async with AsyncSessionLocal() as session:
        email_threads = (
            await session.scalars(
                select(EmailThread)
                .order_by(EmailThread.received_at.desc())
                .limit(50)
            )
        ).all()
        return [serialize_email_thread(thread) for thread in email_threads]
