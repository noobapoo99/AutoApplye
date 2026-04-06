from fastapi import APIRouter, Query
from core.auth_utils import build_gmail_flow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/gmail")
async def gmail_auth() -> dict[str, str]:
    flow = build_gmail_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"auth_url": auth_url}


@router.get("/gmail/callback")
async def gmail_auth_callback(code: str = Query(...)) -> dict[str, str]:
    flow = build_gmail_flow()
    flow.fetch_token(code=code)
    return {
        "status": "success",
        "message": "Gmail OAuth callback validated successfully.",
    }
