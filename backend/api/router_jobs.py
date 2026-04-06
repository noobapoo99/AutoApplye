import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from agents import scout_agent as _scout_agent  # noqa: F401
from agents.base import AgentFactory
from api.schemas import SearchJobsRequest, ReviewDecisionRequest
from core.queue import JD_READY, queue_manager
from core.websocket import ws_manager, event_payload
from db.models import Application, ApplicationStatus, AsyncSessionLocal

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.post("/search")
async def search_jobs(
    request: SearchJobsRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    pipeline_id = str(uuid4())

    async def run_pipeline() -> None:
        await ws_manager.broadcast(
            event_payload(
                "pipeline_started",
                pipeline_id=pipeline_id,
                query=request.query,
                max_jobs=request.max_jobs,
                strategy=request.strategy,
            )
        )

        try:
            scout = AgentFactory.create(
                "scout",
                search_query=request.query,
                max_jobs=request.max_jobs,
            )
            result = await scout.run(
                {
                    "search_query": request.query,
                    "job_id": pipeline_id,
                    "strategy": request.strategy,
                }
            )
            jobs_found = len(result.get("discovered_jobs", []))
            await ws_manager.broadcast(
                event_payload(
                    "scout_complete",
                    pipeline_id=pipeline_id,
                    query=request.query,
                    max_jobs=request.max_jobs,
                    strategy=request.strategy,
                    jobs_found=jobs_found,
                )
            )
        except Exception as exc:
            logger.exception("Pipeline %s failed", pipeline_id)
            await ws_manager.broadcast(
                event_payload(
                    "pipeline_error",
                    pipeline_id=pipeline_id,
                    query=request.query,
                    max_jobs=request.max_jobs,
                    strategy=request.strategy,
                    error=str(exc),
                )
            )

    background_tasks.add_task(run_pipeline)
    return {
        "pipeline_id": pipeline_id,
        "status": "started",
        "query": request.query,
    }


@router.post("/review/{job_id}")
async def review_application(
    job_id: str,
    request: ReviewDecisionRequest,
) -> dict[str, Any]:
    # Note: prefix is /api/jobs, so this is /api/jobs/review/{job_id}
    # Original was /api/review/{job_id}. I'll adjust the prefix or the route to match original URL.
    # Actually original was /api/review/{job_id}. 
    # Let's use APIRouter(prefix="/api", tags=["jobs/review"]) and then @router.post("/review/{job_id}")
    # but the job search was /api/jobs/search. 
    # Let's just define them carefully in main.py.
    if job_id != request.job_id:
        raise HTTPException(status_code=400, detail="Path job_id must match body.job_id")

    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(Application)
            .options(
                selectinload(Application.job),
                selectinload(Application.resume_version),
            )
            .where(Application.job_id == job_id)
        )
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")

        if request.decision == "proceed":
            apply_url = (
                application.job.external_apply_url
                if application.job is not None
                else None
            )
            edited_filename = (
                application.resume_version.edited_filename
                if application.resume_version is not None
                else None
            )
            if not apply_url or not edited_filename:
                raise HTTPException(
                    status_code=409,
                    detail="Application is missing apply URL or edited resume metadata",
                )

            application.status = ApplicationStatus.applying
            resume_path = str(Path("/tmp/resumes") / edited_filename)
            await queue_manager.publish(
                JD_READY,
                {
                    "job_id": application.job_id,
                    "company_name": application.company_name,
                    "role_title": application.role_title,
                    "external_apply_url": apply_url,
                    "resume_path": resume_path,
                    "match_score": application.match_score,
                    "resume_version_id": application.resume_version_id,
                },
                "jd.ready.new",
            )
            await session.commit()
            await ws_manager.broadcast(
                event_payload(
                    "human_approved",
                    job_id=application.job_id,
                    application_id=application.id,
                    status=application.status.value,
                )
            )
        else:
            application.status = ApplicationStatus.withdrawn
            await session.commit()
            await ws_manager.broadcast(
                event_payload(
                    "human_skipped",
                    job_id=application.job_id,
                    application_id=application.id,
                    status=application.status.value,
                )
            )

        await session.refresh(application)
        return {
            "job_id": application.job_id,
            "decision": request.decision,
            "status": application.status.value,
        }
