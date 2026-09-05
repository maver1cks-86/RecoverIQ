from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.decision import RecoveryDecision
from app.models.intervention import Intervention
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch
from app.schemas.audit import AuditEvent, PaymentAuditResponse


def _payment_link_id(payload: dict) -> str | None:
    wrapper = payload.get("payment_link")
    entity = wrapper.get("entity") if isinstance(wrapper, dict) else None
    value = entity.get("id") if isinstance(entity, dict) else None
    return value if isinstance(value, str) else None


def get_payment_audit(db: Session, payment_id: int) -> PaymentAuditResponse | None:
    payment = db.scalar(
        select(Payment)
        .options(
            selectinload(Payment.recovery_decisions)
            .selectinload(RecoveryDecision.interventions)
            .selectinload(Intervention.outcome)
        )
        .where(Payment.id == payment_id)
    )
    if payment is None:
        return None

    events = [
        AuditEvent(
            event_type="PAYMENT",
            title="Payment recorded",
            status=payment.status.value,
            timestamp=payment.created_at,
            details={
                "amount": str(payment.amount),
                "currency": payment.currency,
                "payment_method": payment.payment_method,
                "failure_code": payment.failure_code,
                "failure_reason": payment.failure_reason,
            },
        )
    ]
    assignments = db.scalars(
        select(OptimizationAssignment)
        .options(selectinload(OptimizationAssignment.plan).selectinload(OptimizationPlan.batch))
        .where(OptimizationAssignment.payment_id == payment_id)
        .order_by(OptimizationAssignment.created_at)
    )
    for assignment in assignments:
        events.append(
            AuditEvent(
                event_type="PLAN",
                title="Portfolio assignment persisted",
                status=assignment.selected_action.value,
                timestamp=assignment.created_at,
                details={
                    "batch_id": str(assignment.plan.batch_id),
                    "plan_id": str(assignment.plan_id),
                    "plan_version": assignment.plan.version,
                    "model_version": assignment.plan.model_version,
                    "policy_status": assignment.policy_status.value,
                    "execution_status": assignment.execution_status,
                    "standalone_best_action": assignment.standalone_best_action,
                    "selected_rank": assignment.selected_rank,
                    "portfolio_agreement": assignment.portfolio_agreement,
                    "recovery_probability": assignment.recovery_probability,
                    "expected_value": str(assignment.expected_value),
                    "incremental_value": str(assignment.incremental_value),
                    "intervention_cost": str(assignment.intervention_cost),
                    "incentive_cost": str(assignment.incentive_cost),
                    "alternatives": assignment.alternatives,
                    "policy_evidence": assignment.policy_evidence,
                    "constraints_snapshot": assignment.plan.constraints_snapshot,
                },
            )
        )
    provider_ids: set[str] = set()
    for decision in payment.recovery_decisions:
        events.append(
            AuditEvent(
                event_type="DECISION",
                title="Recovery decision created",
                status=decision.selected_action.value,
                timestamp=decision.created_at,
                details={
                    "predicted_probability": decision.predicted_probability,
                    "expected_value": str(decision.expected_value),
                    "model_version": decision.model_version,
                },
            )
        )
        events.append(
            AuditEvent(
                event_type="POLICY",
                title="Policy evaluation",
                status=decision.policy_status.value,
                timestamp=decision.created_at,
                details={"selected_action": decision.selected_action.value},
            )
        )
        for intervention in decision.interventions:
            if intervention.provider_action_id:
                provider_ids.add(intervention.provider_action_id)
            events.append(
                AuditEvent(
                    event_type="INTERVENTION",
                    title="Intervention created",
                    status=intervention.status.value,
                    timestamp=intervention.created_at,
                    details={
                        "intervention_id": str(intervention.id),
                        "action": intervention.action_type.value,
                        "provider": intervention.provider,
                        "provider_action_id": intervention.provider_action_id,
                        "provider_status": intervention.provider_status,
                    },
                )
            )
            if intervention.provider and intervention.executed_at:
                events.append(
                    AuditEvent(
                        event_type="PROVIDER",
                        title="Provider action executed",
                        status=intervention.provider_status,
                        timestamp=intervention.executed_at,
                        details={
                            "provider": intervention.provider,
                            "provider_action_id": intervention.provider_action_id,
                        },
                    )
                )
            if intervention.outcome is not None:
                outcome = intervention.outcome
                events.append(
                    AuditEvent(
                        event_type="OUTCOME",
                        title="Recovery outcome recorded",
                        status="RECOVERED" if outcome.recovered else "NOT_RECOVERED",
                        timestamp=outcome.completed_at or outcome.created_at,
                        details={
                            "recovered": outcome.recovered,
                            "recovered_amount": str(outcome.recovered_amount),
                            "recovery_time_hours": outcome.recovery_time_hours,
                        },
                    )
                )

    if provider_ids:
        webhooks = db.scalars(
            select(WebhookEvent)
            .where(WebhookEvent.provider == "razorpay")
            .order_by(WebhookEvent.received_at.desc())
            .limit(500)
        )
        for webhook in webhooks:
            payment_link_id = _payment_link_id(webhook.payload)
            if payment_link_id not in provider_ids:
                continue
            events.append(
                AuditEvent(
                    event_type="WEBHOOK",
                    title="Razorpay webhook received",
                    status=webhook.status,
                    timestamp=webhook.provider_created_at or webhook.received_at,
                    details={
                        "event_type": webhook.event_type,
                        "provider_event_id": webhook.provider_event_id,
                        "provider_action_id": payment_link_id,
                    },
                )
            )

    events.sort(key=lambda item: (item.timestamp is None, item.timestamp))
    return PaymentAuditResponse(
        payment_id=payment.id,
        amount=payment.amount,
        currency=payment.currency,
        payment_method=payment.payment_method,
        current_status=payment.status.value,
        events=events,
    )
