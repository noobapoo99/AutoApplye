from typing import Any
from fastapi import APIRouter
from sqlalchemy import func, select

from api.serializers import serialize_status
from core.redis_client import get_redis_client
from db.models import Application, AsyncSessionLocal

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
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
        serialize_status(status): count for status, count in grouped_statuses
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
