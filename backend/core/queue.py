from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import json
import logging
from typing import Any

from core.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

JD_RAW = "jd.raw"
JD_ENRICHED = "jd.enriched"
JD_READY = "jd.ready"
JD_FLAGGED = "jd.flagged"
DLQ_EMAIL = "dlq.email"
DLQ_APPLICATION = "dlq.application"
DLQ_RESEARCH = "dlq.research"
EXCHANGE_NAME = "jd.exchange"

PRIMARY_QUEUES = {
    JD_RAW,
    JD_ENRICHED,
    JD_READY,
    JD_FLAGGED,
}
DLQ_QUEUES = {
    DLQ_EMAIL,
    DLQ_APPLICATION,
    DLQ_RESEARCH,
}
ALL_QUEUES = PRIMARY_QUEUES | DLQ_QUEUES
PRIMARY_TO_DLQ = {
    JD_RAW: DLQ_RESEARCH,
    JD_ENRICHED: DLQ_RESEARCH,
    JD_READY: DLQ_APPLICATION,
    JD_FLAGGED: DLQ_APPLICATION,
}


class QueueManager:
    def __init__(self) -> None:
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._exchange: Any | None = None
        self._queues: dict[str, Any] = {}

    async def connect(self) -> None:
        if (
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
            and len(self._queues) == len(ALL_QUEUES)
        ):
            return

        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()

        import aio_pika

        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            type="topic",
            durable=True,
        )
        self._queues = {}

        for queue_name in sorted(ALL_QUEUES):
            arguments: dict[str, Any] | None = None
            if queue_name in PRIMARY_TO_DLQ:
                arguments = {
                    "x-dead-letter-exchange": EXCHANGE_NAME,
                    "x-dead-letter-routing-key": PRIMARY_TO_DLQ[queue_name],
                }

            queue = await self._channel.declare_queue(
                queue_name,
                durable=True,
                arguments=arguments,
            )
            # Bind to both exact key and wildcard so messages with routing keys
            # like "jd.raw.new" actually reach the "jd.raw" queue.
            await queue.bind(self._exchange, routing_key=queue_name)
            await queue.bind(self._exchange, routing_key=f"{queue_name}.*")
            await queue.bind(self._exchange, routing_key=f"{queue_name}.#")
            self._queues[queue_name] = queue

    async def publish(
        self,
        queue_key: str,
        payload: Any,
        routing_key: str,
    ) -> None:
        self._validate_queue_key(queue_key)
        await self.connect()

        import aio_pika

        message = aio_pika.Message(
            body=json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)

    async def publish_to_dlq(self, queue_key: str, payload: Any, reason: str) -> None:
        dlq_key = self._resolve_dlq_key(queue_key)
        envelope = {
            "failed_queue": queue_key,
            "reason": reason,
            "payload": payload,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.publish(dlq_key, envelope, routing_key=dlq_key)

    async def consume(
        self,
        queue_key: str,
        handler: Callable[[Any], Awaitable[None]],
    ) -> str:
        self._validate_queue_key(queue_key)
        await self.connect()
        queue = self._queues[queue_key]

        async def _callback(message: Any) -> None:
            try:
                payload = json.loads(message.body.decode("utf-8"))
            except Exception as exc:
                logger.exception("Failed to decode message from %s", queue_key)
                await message.ack()
                await self.publish_to_dlq(
                    queue_key,
                    {"raw_body": message.body.decode("utf-8", errors="replace")},
                    f"json_decode_error: {exc}",
                )
                return

            logger.info("Message received from queue: %s", queue_key)
            try:
                await handler(payload)
                await message.ack()
            except Exception as exc:
                logger.exception("Handler failed for queue %s", queue_key)
                await message.ack()
                await self.publish_to_dlq(queue_key, payload, f"handler_error: {exc}")

        return await queue.consume(_callback)

    async def close(self) -> None:
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()

        self._connection = None
        self._channel = None
        self._exchange = None
        self._queues = {}

    def _validate_queue_key(self, queue_key: str) -> None:
        if queue_key not in ALL_QUEUES:
            raise ValueError(f"Unknown queue key: {queue_key}")

    def _resolve_dlq_key(self, queue_key: str) -> str:
        self._validate_queue_key(queue_key)
        if queue_key in DLQ_QUEUES:
            return queue_key
        return PRIMARY_TO_DLQ[queue_key]


queue_manager = QueueManager()


__all__ = [
    "DLQ_APPLICATION",
    "DLQ_EMAIL",
    "DLQ_RESEARCH",
    "EXCHANGE_NAME",
    "JD_ENRICHED",
    "JD_FLAGGED",
    "JD_RAW",
    "JD_READY",
    "QueueManager",
    "queue_manager",
]
