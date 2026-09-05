from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.models.outcome import Outcome
from app.models.webhook_event import WebhookEvent
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch


SUPPORTED_PAYMENT_LINK_EVENTS = {
    "payment_link.paid",
    "payment_link.partially_paid",
    "payment_link.cancelled",
    "payment_link.expired",
}
EVENT_PRECEDENCE = {
    "payment_link.partially_paid": 1,
    "payment_link.expired": 2,
    "payment_link.cancelled": 3,
    "payment_link.paid": 4,
}
STATUS_PRECEDENCE = {
    InterventionStatus.PLANNED: 0,
    InterventionStatus.EXECUTED: 1,
    InterventionStatus.FAILED: 2,
    InterventionStatus.CANCELLED: 3,
    InterventionStatus.SUCCEEDED: 4,
}


class RazorpayWebhookProcessingError(Exception):
    pass


class RazorpayWebhookProcessor:
    def __init__(self, db: Session):
        self.db = db

    def process(
        self,
        webhook_event: WebhookEvent,
    ) -> str:
        """
        Process one persisted Razorpay webhook event.

        Returns:
            "processed"
            "ignored"
            "stale"

        Raises:
            RazorpayWebhookProcessingError
        """

        if webhook_event.event_type not in SUPPORTED_PAYMENT_LINK_EVENTS:
            webhook_event.status = "ignored"
            webhook_event.processed_at = datetime.now(timezone.utc)
            self.db.commit()
            return "ignored"

        payment_link = self._extract_payment_link_entity(
            webhook_event.payload
        )

        payment_link_id = payment_link.get("id")

        if not isinstance(payment_link_id, str) or not payment_link_id:
            raise RazorpayWebhookProcessingError(
                "Payment Link webhook is missing payload.payment_link.entity.id."
            )

        intervention = self.db.scalar(
            select(Intervention).where(
                Intervention.provider == "razorpay",
                Intervention.provider_action_id == payment_link_id,
            )
        )

        if intervention is None:
            raise RazorpayWebhookProcessingError(
                f"No intervention found for Razorpay Payment Link {payment_link_id}."
            )

        event_time = self._event_time(webhook_event)

        if (
            intervention.last_provider_event_at is not None
            and (
                event_time < intervention.last_provider_event_at
                or (
                    event_time == intervention.last_provider_event_at
                    and EVENT_PRECEDENCE[webhook_event.event_type]
                    < STATUS_PRECEDENCE[intervention.status]
                )
            )
        ):
            webhook_event.status = "stale"
            webhook_event.processed_at = datetime.now(timezone.utc)
            self.db.commit()
            return "stale"

        # Successful recovery is terminal. Later partial/cancel/expiry events are
        # acknowledged but cannot change provider, intervention, payment or outcome.
        if (
            intervention.status is InterventionStatus.SUCCEEDED
            and webhook_event.event_type != "payment_link.paid"
        ):
            webhook_event.status = "processed"
            webhook_event.processed_at = datetime.now(timezone.utc)
            self.db.commit()
            return "processed"

        provider_status = payment_link.get("status")

        if isinstance(provider_status, str):
            intervention.provider_status = provider_status

        intervention.last_provider_event_at = event_time

        if webhook_event.event_type == "payment_link.paid":
            self._apply_paid(
                intervention=intervention,
                payment_link=payment_link,
                event_time=event_time,
            )
            self._sync_assignment_recovered(intervention, provider_status)

        elif webhook_event.event_type == "payment_link.partially_paid":
            self._apply_partially_paid(
                intervention=intervention,
                payment_link=payment_link,
                event_time=event_time,
            )

        elif webhook_event.event_type == "payment_link.cancelled":
            self._apply_cancelled(
                intervention=intervention,
                event_time=event_time,
            )

        elif webhook_event.event_type == "payment_link.expired":
            self._apply_expired(
                intervention=intervention,
                event_time=event_time,
            )

        webhook_event.status = "processed"
        webhook_event.processed_at = datetime.now(timezone.utc)

        self.db.commit()

        return "processed"

    @staticmethod
    def _extract_payment_link_entity(
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payment_link_wrapper = payload.get("payment_link")

        if not isinstance(payment_link_wrapper, dict):
            raise RazorpayWebhookProcessingError(
                "Webhook payload is missing payment_link."
            )

        entity = payment_link_wrapper.get("entity")

        if not isinstance(entity, dict):
            raise RazorpayWebhookProcessingError(
                "Webhook payload is missing payment_link.entity."
            )

        return entity

    @staticmethod
    def _event_time(
        webhook_event: WebhookEvent,
    ) -> datetime:
        if webhook_event.provider_created_at is not None:
            return webhook_event.provider_created_at

        return webhook_event.received_at

    @staticmethod
    def _ensure_outcome(
        intervention: Intervention,
    ) -> Outcome:
        if intervention.outcome is not None:
            return intervention.outcome

        outcome = Outcome(
            recovered=False,
            recovered_amount=Decimal("0.00"),
        )

        intervention.outcome = outcome

        return outcome

    def _apply_paid(
        self,
        *,
        intervention: Intervention,
        payment_link: dict[str, Any],
        event_time: datetime,
    ) -> None:
        intervention.status = InterventionStatus.SUCCEEDED

        outcome = self._ensure_outcome(intervention)

        amount_paid_paise = payment_link.get("amount_paid")

        if isinstance(amount_paid_paise, int):
            recovered_amount = (
                Decimal(amount_paid_paise) / Decimal("100")
            )
        else:
            recovered_amount = intervention.decision.payment.amount

        outcome.recovered = True
        outcome.recovered_amount = recovered_amount
        outcome.completed_at = event_time

        payment = intervention.decision.payment
        payment.status = PaymentStatus.RECOVERED

    def _apply_partially_paid(
        self,
        *,
        intervention: Intervention,
        payment_link: dict[str, Any],
        event_time: datetime,
    ) -> None:
        if intervention.status is InterventionStatus.SUCCEEDED:
            return
        if intervention.status not in {
            InterventionStatus.SUCCEEDED,
            InterventionStatus.CANCELLED,
            InterventionStatus.FAILED,
        }:
            intervention.status = InterventionStatus.EXECUTED

        outcome = self._ensure_outcome(intervention)

        amount_paid_paise = payment_link.get("amount_paid")

        if isinstance(amount_paid_paise, int):
            outcome.recovered_amount = (
                Decimal(amount_paid_paise) / Decimal("100")
            )

        outcome.recovered = False
        outcome.completed_at = None

    def _sync_assignment_recovered(
        self,
        intervention: Intervention,
        provider_status: object,
    ) -> None:
        assignment = self.db.scalar(
            select(OptimizationAssignment).where(
                OptimizationAssignment.intervention_id == intervention.id
            )
        )
        if assignment is None:
            return
        assignment.execution_status = "RECOVERED"
        assignment.provider_status = (
            provider_status if isinstance(provider_status, str) else "paid"
        )
        plan = self.db.get(OptimizationPlan, assignment.plan_id)
        if plan is None:
            return
        active = self.db.scalar(
            select(func.count()).select_from(OptimizationAssignment).where(
                OptimizationAssignment.plan_id == plan.id,
                OptimizationAssignment.execution_status.in_(
                    ["PLANNED", "QUEUED", "EXECUTING", "AWAITING_PAYMENT"]
                ),
            )
        )
        if active == 0:
            batch = self.db.get(RecoveryBatch, plan.batch_id)
            if batch is not None:
                batch.status = "COMPLETED"
                batch.execution_completed_at = datetime.now(timezone.utc)

    def _apply_cancelled(
        self,
        *,
        intervention: Intervention,
        event_time: datetime,
    ) -> None:
        if intervention.status == InterventionStatus.SUCCEEDED:
            return

        intervention.status = InterventionStatus.CANCELLED

        outcome = self._ensure_outcome(intervention)
        outcome.recovered = False
        outcome.completed_at = event_time

    def _apply_expired(
        self,
        *,
        intervention: Intervention,
        event_time: datetime,
    ) -> None:
        if intervention.status == InterventionStatus.SUCCEEDED:
            return

        intervention.status = InterventionStatus.FAILED

        outcome = self._ensure_outcome(intervention)
        outcome.recovered = False
        outcome.completed_at = event_time
