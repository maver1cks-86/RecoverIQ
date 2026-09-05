from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.integrations.razorpay.webhooks import (
    RazorpayWebhookPayloadError,
    RazorpayWebhookSignatureError,
    parse_webhook_event,
    verify_webhook_signature,
)
from app.repositories.webhook_repository import WebhookRepository
from app.tasks.webhook_tasks import (
    TERMINAL_WEBHOOK_STATUSES,
    process_razorpay_webhook,
)

router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(
        default=None,
        alias="X-Razorpay-Signature",
    ),
    x_razorpay_event_id: str | None = Header(
        default=None,
        alias="x-razorpay-event-id",
    ),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    try:
        verify_webhook_signature(
            raw_body=raw_body,
            received_signature=x_razorpay_signature or "",
            webhook_secret=settings.RAZORPAY_WEBHOOK_SECRET,
        )
    except RazorpayWebhookSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    try:
        event = parse_webhook_event(
            raw_body=raw_body,
            event_id=x_razorpay_event_id or "",
        )
    except RazorpayWebhookPayloadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    repository = WebhookRepository(db)

    stored_event, created = repository.record_razorpay_event(event)

    # A webhook that already reached a terminal processing state must
    # never be applied again.
    if not created and stored_event.status in TERMINAL_WEBHOOK_STATUSES:
        return {
            "status": "duplicate",
            "event_id": stored_event.provider_event_id,
            "event_type": stored_event.event_type,
            "processing_status": stored_event.status,
        }

    # New events and duplicates in a non-terminal state are queued.
    # In particular, a failed event can be retried by a later provider
    # delivery while the unique database row preserves idempotency.
    process_razorpay_webhook.delay(stored_event.id)

    return {
        "status": "queued",
        "event_id": stored_event.provider_event_id,
        "event_type": stored_event.event_type,
    }
