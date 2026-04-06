from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend root is in sys.path
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Core imports
from core.config import get_settings
from core.queue import queue_manager
from core.websocket import ws_manager
from db.models import init_db

# Router imports
from api.router_jobs import router as jobs_router
from api.router_applications import router as applications_router
from api.router_auth import router as auth_router
from api.router_user import router as user_router
from api.router_stats import router as stats_router

# Logging setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, get_settings().log_level.upper(), logging.INFO))
settings = get_settings()

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Initializing database with URL: %s", get_settings().database_url)
    await init_db()
    await queue_manager.connect()
    try:
        yield
    finally:
        await queue_manager.close()


app = FastAPI(
    title="AutoApply API",
    version=APP_VERSION,
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket Logs
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


# Health Check
@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


# Include Routers
# Note: router prefixes are defined within the router files themselves
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(stats_router)
