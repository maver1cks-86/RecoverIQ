from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError

from app.services.batch_event_service import subscribe_batch_events


router = APIRouter(tags=["batch-stream"])


@router.websocket("/ws/batches/{batch_id}")
async def batch_status_stream(websocket: WebSocket, batch_id: int) -> None:
    await websocket.accept()
    try:
        async for event in subscribe_batch_events(batch_id):
            await websocket.send_json(event)
    except (WebSocketDisconnect, RedisError):
        # Database workflows remain authoritative and must not depend on sockets.
        return
