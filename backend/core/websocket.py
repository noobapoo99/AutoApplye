import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


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
        """Broadcasts a JSON message to all currently connected WebSockets in this process."""
        dead_connections: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)

    async def publish_event(self, event_type: str, **kwargs: Any) -> None:
        """
        Publishes an event to Redis Pub/Sub.
        This is used by workers to send events to the API process.
        """
        from core.redis_client import get_redis_client

        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        try:
            client = get_redis_client()
            await client.publish("agent_events", json.dumps(payload, default=str))
        except Exception as exc:
            logger.error("Failed to publish event to Redis: %s", exc)


ws_manager = ConnectionManager()


async def redis_event_listener() -> None:
    """
    Subscribes to the 'agent_events' Redis channel and broadcasts 
    every message received to all connected WebSockets.
    Should be run as a background task in the API lifespan.
    """
    from core.redis_client import get_redis_client

    client = get_redis_client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe("agent_events")
        logger.info("Subscribed to Redis 'agent_events' channel")

        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await ws_manager.broadcast(data)
                except Exception as exc:
                    logger.warning("Failed to decode or broadcast Redis event: %s", exc)
    except Exception as exc:
        logger.error("Redis event listener crashed: %s", exc)
    finally:
        await pubsub.unsubscribe("agent_events")
