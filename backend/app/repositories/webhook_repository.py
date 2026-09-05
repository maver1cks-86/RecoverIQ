from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.integrations.razorpay.webhooks import RazorpayWebhookEvent
from app.models.webhook_event import WebhookEvent


class WebhookRepository:
    def __init__(self, db: Session):
        self.db = db

    def record_razorpay_event(
        self,
        event: RazorpayWebhookEvent,
    ) -> tuple[WebhookEvent, bool]:
        """
        Persist a Razorpay webhook event idempotently.

        Returns:
            (webhook_event, created)

        created=True:
            This event ID was inserted for the first time.

        created=False:
            This event ID already existed.
        """

        provider_created_at = None

        if event.created_at is not None:
            provider_created_at = datetime.fromtimestamp(
                event.created_at,
                tz=timezone.utc,
            )

        statement = (
            insert(WebhookEvent)
            .values(
                provider="razorpay",
                provider_event_id=event.event_id,
                event_type=event.event_type,
                account_id=event.account_id,
                payload=event.payload,
                status="received",
                provider_created_at=provider_created_at,
            )
            .on_conflict_do_nothing(
                constraint="uq_webhook_provider_event"
            )
            .returning(WebhookEvent.id)
        )

        inserted_id = self.db.execute(
            statement
        ).scalar_one_or_none()

        self.db.commit()

        if inserted_id is not None:
            stored_event = self.db.get(
                WebhookEvent,
                inserted_id,
            )

            if stored_event is None:
                raise RuntimeError(
                    "Inserted webhook event could not be loaded."
                )

            return stored_event, True

        existing_event = self.db.scalar(
            select(WebhookEvent).where(
                WebhookEvent.provider == "razorpay",
                WebhookEvent.provider_event_id == event.event_id,
            )
        )

        if existing_event is None:
            raise RuntimeError(
                "Duplicate webhook event could not be loaded."
            )

        return existing_event, False