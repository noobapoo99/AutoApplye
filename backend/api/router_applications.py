from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.serializers import (
    serialize_application_summary,
    serialize_application_detail,
    serialize_datetime,
)
from core.config import get_settings
from core.queue import JD_ENRICHED, queue_manager
from core.resume_store import DATA_DIR
from db.models import Application, ApplicationStatus, AsyncSessionLocal, ResumeVersion, Job

router = APIRouter(prefix="/api", tags=["applications"])
settings = get_settings()
BACKEND_ROOT = DATA_DIR.parent


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
                "resume_version_id": application.resume_version_id,
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


@router.get("/applications/resume/{resume_version_id}")
async def get_resume_file(resume_version_id: str) -> FileResponse:
    async with AsyncSessionLocal() as session:
        version = await session.get(ResumeVersion, resume_version_id)
        if not version or not version.edited_filename:
            raise HTTPException(status_code=404, detail="Resume version not found")

        resume_dir = Path(settings.RESUME_DIR)
        if not resume_dir.is_absolute():
            if settings.RESUME_DIR.startswith("data/"):
                resume_dir = DATA_DIR / Path(settings.RESUME_DIR).relative_to("data")
            else:
                resume_dir = BACKEND_ROOT / settings.RESUME_DIR
            
        resume_path = resume_dir / version.edited_filename
        if not resume_path.exists():
            raise HTTPException(
                status_code=404, 
                detail=f"Resume file not found on disk at {resume_path.absolute()}. Please ensure the resume worker is running and sharing the volume."
            )

        return FileResponse(
            path=str(resume_path),
            filename=version.edited_filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


@router.post("/applications/{application_id}/status")
async def update_status(application_id: str, payload: dict[str, Any]) -> dict[str, str]:
    new_status = payload.get("status")
    if not new_status or new_status not in [s.value for s in ApplicationStatus]:
        raise HTTPException(status_code=400, detail="Invalid status")

    async with AsyncSessionLocal() as session:
        application = await session.get(Application, application_id)
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        application.status = ApplicationStatus(new_status)
        
        # Also update parent Job row
        job = await session.get(Job, application.job_id)
        if job:
            job.status = ApplicationStatus(new_status)
            
        await session.commit()
    
    return {"status": "ok", "new_status": new_status}


@router.post("/applications/{application_id}/rerun")
async def rerun_pipeline(application_id: str) -> dict[str, str]:
    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(Application)
            .options(selectinload(Application.job))
            .where(Application.id == application_id)
        )
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")

        # Set status back to researching or resume_editing to reflect re-run
        application.status = ApplicationStatus.resume_editing
        if application.job:
            application.job.status = ApplicationStatus.resume_editing
            
        await queue_manager.publish(
            JD_ENRICHED,
            {
                "job_id": application.job_id,
                "company_name": application.company_name,
                "role_title": application.role_title,
                "jd_text": application.job.raw_text if application.job else "",
            },
            "jd.enriched.manual_rerun"
        )
        
        await session.commit()

    return {"status": "queued"}
