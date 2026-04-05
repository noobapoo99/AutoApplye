from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any, Literal
from uuid import uuid4

from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import UploadFile
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import selectinload


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agents import scout_agent as _scout_agent  # noqa: F401
from agents.base import AgentFactory
from core.config import get_settings
from core.queue import JD_READY
from core.queue import queue_manager
from core.redis_client import get_redis_client
from core.resume_store import get_resume_metadata
from core.resume_store import get_user_profile
from core.resume_store import save_resume
from core.resume_store import save_user_profile
from db.models import Application
from db.models import ApplicationStatus
from db.models import AsyncSessionLocal
from db.models import EmailThread
from db.models import init_db


logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, get_settings().log_level.upper(), logging.INFO))
settings = get_settings()

APP_VERSION = "1.0.0"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": settings.GMAIL_CLIENT_ID,
        "client_secret": settings.GMAIL_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [settings.GMAIL_REDIRECT_URI],
    }
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await queue_manager.connect()
    try:
        yield
    finally:
        await queue_manager.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead_connections: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)


ws_manager = ConnectionManager()


class SearchJobsRequest(BaseModel):
    query: str
    max_jobs: int = 5
    strategy: str = "keyword_injection"


class ReviewDecisionRequest(BaseModel):
    job_id: str
    decision: Literal["proceed", "skip"]


class UserDataRequest(BaseModel):
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone: str
    linkedin_url: str
    github_url: str | None = None


@app.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)


@app.post("/api/jobs/search")
async def search_jobs(
    request: SearchJobsRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    pipeline_id = str(uuid4())

    async def run_pipeline() -> None:
        await ws_manager.broadcast(
            _event_payload(
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
                _event_payload(
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
                _event_payload(
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


@app.post("/api/review/{job_id}")
async def review_application(
    job_id: str,
    request: ReviewDecisionRequest,
) -> dict[str, Any]:
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
                _event_payload(
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
                _event_payload(
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


@app.get("/api/applications")
async def list_applications() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        applications = (
            await session.scalars(
                select(Application).order_by(Application.last_updated.desc())
            )
        ).all()
        return [_serialize_application_summary(application) for application in applications]


@app.get("/api/applications/{application_id}")
async def get_application(application_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        application = await session.scalar(
            select(Application)
            .options(selectinload(Application.email_threads))
            .where(Application.id == application_id)
        )
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")

        return _serialize_application_detail(application)


@app.get("/api/flagged")
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
                "last_updated": _serialize_datetime(application.last_updated),
            }
            for application in applications
        ]


@app.get("/api/emails")
async def list_emails() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        email_threads = (
            await session.scalars(
                select(EmailThread)
                .order_by(EmailThread.received_at.desc())
                .limit(50)
            )
        ).all()
        return [_serialize_email_thread(thread) for thread in email_threads]


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        total_applications = (
            await session.scalar(select(func.count(Application.id)))
        ) or 0
        average_match_score = await session.scalar(select(func.avg(Application.match_score)))
        grouped_statuses = (
            await session.execute(
                select(Application.status, func.count(Application.id)).group_by(
                    Application.status
                )
            )
        ).all()

    status_breakdown = {
        _serialize_status(status): count for status, count in grouped_statuses
    }

    try:
        cache_connected = bool(await get_redis_client().ping())
    except Exception:
        cache_connected = False

    return {
        "total_applications": int(total_applications),
        "status_breakdown": status_breakdown,
        "avg_match_score": float(average_match_score or 0.0),
        "cache_connected": cache_connected,
    }


@app.get("/auth/gmail")
async def gmail_auth() -> dict[str, str]:
    flow = _build_gmail_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"auth_url": auth_url}


@app.get("/auth/gmail/callback")
async def gmail_auth_callback(code: str = Query(...)) -> dict[str, str]:
    flow = _build_gmail_flow()
    flow.fetch_token(code=code)
    return {
        "status": "success",
        "message": "Gmail OAuth callback validated successfully.",
    }


@app.post("/api/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    Upload a user resume (.docx or .pdf).
    The file is stored as the canonical `base_resume.docx` used by all agents.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="No filename provided")

    allowed_extensions = {".pdf", ".docx"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid file type '{suffix}'. Only .pdf and .docx are accepted.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        metadata = save_resume(file_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to save resume: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process resume file") from exc

    return {"status": "ok", **metadata}


@app.get("/api/resume/status")
async def resume_status() -> dict[str, Any]:
    """Return whether a base resume is stored and its metadata."""
    metadata = get_resume_metadata()
    if metadata is None:
        return {"uploaded": False}
    return metadata


@app.get("/api/user/profile")
async def get_profile() -> dict[str, Any]:
    """Return the stored user profile (name, email, phone, LinkedIn…)."""
    profile = get_user_profile()
    if profile is None:
        return {}
    return profile


@app.post("/api/user/profile")
async def save_profile(request: UserDataRequest) -> dict[str, Any]:
    """Persist user profile used by the application agent to fill forms."""
    profile_data = request.model_dump(exclude_none=True)
    saved = save_user_profile(profile_data)
    return {"status": "ok", **saved}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


def _build_gmail_flow() -> Flow:
    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
    )
    return flow


def _serialize_application_summary(application: Application) -> dict[str, Any]:
    return {
        "id": application.id,
        "job_id": application.job_id,
        "company_name": application.company_name,
        "role_title": application.role_title,
        "status": application.status.value,
        "match_score": application.match_score,
        "applied_at": _serialize_datetime(application.applied_at),
        "last_updated": _serialize_datetime(application.last_updated),
    }


def _serialize_application_detail(application: Application) -> dict[str, Any]:
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
        "applied_at": _serialize_datetime(application.applied_at),
        "last_updated": _serialize_datetime(application.last_updated),
        "resume_version_id": application.resume_version_id,
        "flagged_reason": application.flagged_reason,
        "hallucination_score": application.hallucination_score,
        "notes": application.notes,
        "form_fill_result": application.form_fill_result,
        "email_threads": [_serialize_email_thread(thread) for thread in email_threads],
    }


def _serialize_email_thread(thread: EmailThread) -> dict[str, Any]:
    return {
        "id": thread.id,
        "application_id": thread.application_id,
        "gmail_thread_id": thread.gmail_thread_id,
        "subject": thread.subject,
        "sender": thread.sender,
        "classification": thread.classification,
        "ai_summary": thread.ai_summary,
        "draft_followup": thread.draft_followup,
        "received_at": _serialize_datetime(thread.received_at),
        "dlq_attempts": thread.dlq_attempts,
    }


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _serialize_status(value: ApplicationStatus | str | None) -> str:
    if isinstance(value, ApplicationStatus):
        return value.value
    return str(value or "")


def _event_payload(event: str, **extra: Any) -> dict[str, Any]:
    return {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }

