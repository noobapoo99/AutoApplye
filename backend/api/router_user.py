import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas import UserDataRequest
from core.resume_store import (
    get_resume_metadata,
    get_user_profile,
    save_resume,
    save_user_profile,
)

router = APIRouter(prefix="/api", tags=["user"])
logger = logging.getLogger(__name__)


@router.post("/resume/upload")
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


@router.get("/resume/status")
async def resume_status() -> dict[str, Any]:
    """Return whether a base resume is stored and its metadata."""
    metadata = get_resume_metadata()
    if metadata is None:
        return {"uploaded": False}
    return metadata


@router.get("/user/profile")
async def get_profile() -> dict[str, Any]:
    """Return the stored user profile (name, email, phone, LinkedIn…)."""
    profile = get_user_profile()
    if profile is None:
        return {}
    return profile


@router.post("/user/profile")
async def save_profile(request: UserDataRequest) -> dict[str, Any]:
    """Persist user profile used by the application agent to fill forms."""
    profile_data = request.model_dump(exclude_none=True)
    saved = save_user_profile(profile_data)
    return {"status": "ok", **saved}
