from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import redis
import redis.asyncio as async_redis
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.outcome import Outcome
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan


logger = logging.getLogger(__name__)


class BatchStatusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(pattern=r"^(batch|assignment|payment)\.updated$")
    batch_id: int = Field(ge=1)
    payment_id: int | None = Field(default=None, ge=1)
    assignment_id: int | None = Field(default=None, ge=1)
    status: str | None = None
    execution_status: str | None = None
    provider_status: str | None = None
    provider_action_id: str | None = None
    recovered_amount: float | None = Field(default=None, ge=0)


def batch_channel(batch_id: int) -> str:
    return f"recoveriq:batch:{batch_id}"


def publish_batch_event(event: BatchStatusEvent) -> bool:
    """Best-effort notification after a committed database change."""
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.publish(batch_channel(event.batch_id), event.model_dump_json())
        client.close()
        return True
    except redis.RedisError as exc:
        logger.warning(
            "recoveriq.batch_event.publish_failed batch_id=%s error=%s",
            event.batch_id,
            type(exc).__name__,
        )
        return False


def publish_assignment_state(
    db: Session,
    assignment: OptimizationAssignment,
    *,
    event_type: str = "assignment.updated",
) -> bool:
    plan = db.get(OptimizationPlan, assignment.plan_id)
    if plan is None:
        return False
    outcome = None
    if assignment.intervention_id is not None:
        outcome = db.scalar(
            select(Outcome).where(Outcome.intervention_id == assignment.intervention_id)
        )
    return publish_batch_event(
        BatchStatusEvent(
            type=event_type,
            batch_id=plan.batch_id,
            payment_id=assignment.payment_id,
            assignment_id=assignment.id,
            status=(
                assignment.payment.status.value
                if assignment.payment is not None
                else None
            ),
            execution_status=assignment.execution_status,
            provider_status=assignment.provider_status,
            provider_action_id=assignment.provider_action_id,
            recovered_amount=(
                float(outcome.recovered_amount)
                if outcome is not None and outcome.recovered
                else None
            ),
        )
    )


async def subscribe_batch_events(batch_id: int) -> AsyncIterator[dict[str, Any]]:
    client = async_redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(batch_channel(batch_id))
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=15.0,
            )
            if message is None:
                yield {"type": "heartbeat", "batch_id": batch_id}
                continue
            payload = json.loads(message["data"])
            yield BatchStatusEvent.model_validate(payload).model_dump(mode="json")
    finally:
        await pubsub.unsubscribe(batch_channel(batch_id))
        await pubsub.aclose()
        await client.aclose()
