from __future__ import annotations

from celery import Task

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.webhook_event import WebhookEvent
from app.models.intervention import Intervention
from app.models.recovery_batch import OptimizationAssignment
from app.services.batch_event_service import publish_assignment_state
from app.services.razorpay_webhook_processor import (
    RazorpayWebhookProcessingError,
    RazorpayWebhookProcessor,
)


TERMINAL_WEBHOOK_STATUSES = {
    "processed",
    "ignored",
    "stale",
}


def _mark_failed(db, webhook_event_id: int) -> None:
    db.rollback()
    webhook_event = db.get(WebhookEvent, webhook_event_id)

    if (
        webhook_event is not None
        and webhook_event.status not in TERMINAL_WEBHOOK_STATUSES
    ):
        webhook_event.status = "failed"
        db.commit()


@celery_app.task(
    bind=True,
    name="app.tasks.webhook_tasks.process_razorpay_webhook",
    max_retries=5,
)
def process_razorpay_webhook(
    self: Task,
    webhook_event_id: int,
) -> dict[str, str | int]:
    """Process one persisted Razorpay webhook in a fresh DB session."""
    db = SessionLocal()

    try:
        webhook_event = db.get(
            WebhookEvent,
            webhook_event_id,
            with_for_update=True,
        )

        if webhook_event is None:
            raise LookupError(
                f"WebhookEvent {webhook_event_id} was not found."
            )

        if webhook_event.status in TERMINAL_WEBHOOK_STATUSES:
            return {
                "status": "skipped",
                "webhook_event_id": webhook_event.id,
                "processing_status": webhook_event.status,
            }

        processing_status = RazorpayWebhookProcessor(db).process(
            webhook_event
        )

        payment_link = webhook_event.payload.get("payment_link", {})
        entity = payment_link.get("entity", {}) if isinstance(payment_link, dict) else {}
        provider_action_id = entity.get("id") if isinstance(entity, dict) else None
        if isinstance(provider_action_id, str):
            assignment = db.query(OptimizationAssignment).join(
                Intervention,
                OptimizationAssignment.intervention_id == Intervention.id,
            ).filter(Intervention.provider_action_id == provider_action_id).one_or_none()
            if assignment is not None:
                publish_assignment_state(db, assignment, event_type="payment.updated")

        return {
            "status": processing_status,
            "webhook_event_id": webhook_event.id,
            "processing_status": processing_status,
        }

    except LookupError:
        db.rollback()
        raise

    except RazorpayWebhookProcessingError:
        _mark_failed(db, webhook_event_id)
        raise

    except Exception as exc:
        _mark_failed(db, webhook_event_id)
        countdown = 2 ** min(self.request.retries, 5)
        raise self.retry(
            exc=exc,
            countdown=countdown,
            max_retries=5,
        )

    finally:
        db.close()
