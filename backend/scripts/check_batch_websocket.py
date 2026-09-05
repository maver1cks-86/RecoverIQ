"""Non-mutating Redis → FastAPI WebSocket connectivity check."""

import asyncio
import json
import sys
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.batch_event_service import BatchStatusEvent, publish_batch_event  # noqa: E402


async def main(batch_id: int) -> None:
    async with websockets.connect(f"ws://127.0.0.1:8000/ws/batches/{batch_id}") as socket:
        await asyncio.sleep(0.2)
        event = BatchStatusEvent(
            type="batch.updated",
            batch_id=batch_id,
            status="CONNECTIVITY_CHECK",
        )
        await asyncio.to_thread(publish_batch_event, event)
        while True:
            received = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
            if received.get("type") != "heartbeat":
                break
        if received != event.model_dump(mode="json"):
            raise RuntimeError("WebSocket event did not match the published event.")
        print(f"BATCH_WEBSOCKET_CONNECTED batch_id={batch_id}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
