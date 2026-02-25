"""Server-Sent Events stream endpoint for real-time notifications."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from pearl.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Stream"])

# Redis pub/sub channel prefix
_CHANNEL_PREFIX = "pearl:events"


async def _event_generator(request: Request, user_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events from Redis pub/sub for the authenticated user."""
    redis = getattr(request.app.state, "redis", None)

    if redis is None:
        # No Redis — send a single keepalive and close
        yield "data: {\"type\": \"connected\", \"message\": \"SSE active (no Redis — polling recommended)\"}\n\n"
        return

    # Subscribe to user-specific and broadcast channels
    channels = [
        f"{_CHANNEL_PREFIX}:user:{user_id}",
        f"{_CHANNEL_PREFIX}:broadcast",
    ]

    pubsub = redis.pubsub()
    await pubsub.subscribe(*channels)
    logger.info("SSE subscriber connected (user=%s)", user_id)

    try:
        # Send connected event
        yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"

        while True:
            if await request.is_disconnected():
                break

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if message and message.get("type") == "message":
                data = message.get("data", "")
                if isinstance(data, bytes):
                    data = data.decode()
                yield f"data: {data}\n\n"
            else:
                # Keepalive comment
                yield ": keepalive\n\n"

            await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
        logger.info("SSE subscriber disconnected (user=%s)", user_id)


@router.get("/stream/events")
async def stream_events(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Stream real-time events via SSE for the authenticated user."""
    user_id = current_user.get("sub", "anonymous")

    return StreamingResponse(
        _event_generator(request, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


async def publish_event(redis, event_type: str, payload: dict, user_id: str | None = None) -> None:
    """Publish an event to the appropriate Redis channel.

    Args:
        redis: Redis connection
        event_type: Event type string (e.g. "approval_created", "finding_ingested")
        payload: Event data dict
        user_id: If set, publish to user-specific channel; else broadcast
    """
    if redis is None:
        return

    event = json.dumps({"type": event_type, **payload})
    channel = (
        f"{_CHANNEL_PREFIX}:user:{user_id}"
        if user_id
        else f"{_CHANNEL_PREFIX}:broadcast"
    )
    try:
        await redis.publish(channel, event)
    except Exception as exc:
        logger.warning("Failed to publish SSE event: %s", exc)
