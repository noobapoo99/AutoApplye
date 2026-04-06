#!/usr/bin/env python3
"""
Worker entry point. WORKER_TYPE env var selects which queue to consume.
Values: research | resume | application | gmail
"""
import os, asyncio
import structlog

# Import all agent modules to trigger @AgentFactory.register() decorators
import agents.scout_agent
import agents.research_agent
import agents.resume_agent
import agents.application_agent
import agents.gmail_agent

from core.queue import queue_manager, JD_RAW, JD_ENRICHED, JD_READY
from agents.base import AgentFactory

logger = structlog.get_logger()
WORKER_TYPE = os.environ.get("WORKER_TYPE", "research")

# Maps worker type → which queue to consume
QUEUE_MAP = {
    "research":    JD_RAW,
    "resume":      JD_ENRICHED,
    "application": JD_READY,
}

async def run_queue_worker():
    queue_key = QUEUE_MAP[WORKER_TYPE]
    await queue_manager.connect()
    agent = AgentFactory.create(WORKER_TYPE)
    logger.info("Worker started", type=WORKER_TYPE, queue=queue_key)

    async def handle(payload: dict):
        await agent.run(payload)

    await queue_manager.consume(queue_key, handle)
    # Run forever — future never resolves
    await asyncio.get_event_loop().create_future()

async def run_gmail_worker():
    from db.models import AsyncSessionLocal, Application, ApplicationStatus
    from agents.gmail_agent import GmailTrackerAgent
    from sqlalchemy import select

    await queue_manager.connect()
    logger.info("Gmail worker started, polling every 30 minutes")

    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Application).where(
                        Application.status == ApplicationStatus.applied
                    )
                )
                applications = result.scalars().all()
                logger.info("Gmail poll", checking=len(applications))

                for app in applications:
                    agent = GmailTrackerAgent(credentials=None)
                    try:
                        await agent.run({
                            "application_id": app.id,
                            "company_name": app.company_name,
                            "role_title": app.role_title,
                        })
                    except Exception as e:
                        logger.error("Gmail agent error", app_id=app.id, error=str(e))
        except Exception as e:
            logger.error("Gmail poll error", error=str(e))

        await asyncio.sleep(1800)  # 30 minutes

if __name__ == "__main__":
    if WORKER_TYPE == "gmail":
        asyncio.run(run_gmail_worker())
    elif WORKER_TYPE in QUEUE_MAP:
        asyncio.run(run_queue_worker())
    else:
        raise ValueError(f"Unknown WORKER_TYPE: {WORKER_TYPE}")
