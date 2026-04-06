from google_auth_oauthlib.flow import Flow
from core.config import get_settings

settings = get_settings()

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


def build_gmail_flow() -> Flow:
    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
    )
    return flow
