from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.models.decision import RecoveryDecision as RecoveryDecisionModel
from app.models.enums import InterventionStatus, PolicyStatus
from app.models.intervention import Intervention
from app.models.payment import Payment
from app.orchestration.state import RecoveryWorkflowState
from app.services.recovery_service import RecoveryService


class RecoveryWorkflowError(Exception):
    """Deterministic workflow/domain failure that should not be retried forever."""


def get_recovery_service() -> RecoveryService:
    return RecoveryService()


def _tenure_days(created_at: datetime | None) -> int:
    if created_at is None:
        return 0
    value = created_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - value).days)


def _build_context(payment: Payment) -> dict:
    customer = payment.customer
    failed_payments = int(customer.failed_payments)
    historical_recovery_rate = (
        float(customer.previous_recoveries) / failed_payments
        if failed_payments > 0
        else 0.0
    )
    created_at = payment.created_at

    return {
        "amount": float(payment.amount),
        "attempt_number": max(1, int(payment.attempt_count)),
        "hour": int(created_at.hour) if created_at is not None else 0,
        "day_of_week": (
            int(created_at.weekday()) if created_at is not None else 0
        ),
        "customer_tenure_days": _tenure_days(customer.created_at),
        "successful_payments": int(customer.successful_payments),
        "failed_payments": failed_payments,
        "previous_recoveries": int(customer.previous_recoveries),
        "historical_recovery_rate": historical_recovery_rate,
        "avg_transaction_value": float(customer.avg_transaction_value),
        # These behavioral rates are not yet persisted in the Phase 22 schema.
        # Neutral explicit defaults keep orchestration separate from ML logic.
        "whatsapp_response_rate": 0.0,
        "email_response_rate": 0.0,
        "retry_success_rate": historical_recovery_rate,
        "payment_link_conversion_rate": 0.0,
        "price_sensitivity": 0.5,
        "payment_method": payment.payment_method,
        "failure_code": payment.failure_code or "UNKNOWN",
        "failure_type": "UNKNOWN",
        "customer_contact_count": 0,
    }


def load_context(state: RecoveryWorkflowState) -> dict:
    payment_id = int(state["payment_id"])

    with SessionLocal() as db:
        payment = db.scalar(
            select(Payment)
            .options(joinedload(Payment.customer))
            .where(Payment.id == payment_id)
        )

        if payment is None:
            raise RecoveryWorkflowError(f"Payment {payment_id} was not found.")

        return {
            "merchant_id": payment.merchant_id,
            "context": _build_context(payment),
            "next_step": "evaluate_recovery",
            "error": None,
        }


def evaluate_recovery(state: RecoveryWorkflowState) -> dict:
    context = state.get("context")
    if context is None:
        raise RecoveryWorkflowError("Recovery context has not been loaded.")

    planned_action = state.get("planned_action")
    if planned_action is not None:
        return {
            "selected_action": RecoveryAction(planned_action).value,
            "policy_status": state.get("planned_policy_status") or PolicyStatus.ALLOWED.value,
            "predicted_probability": float(state.get("planned_probability") or 0.0),
            "expected_value": float(state.get("planned_expected_value") or 0.0),
            "incremental_value": float(state.get("planned_incremental_value") or 0.0),
            "intervention_cost": float(state.get("planned_intervention_cost") or 0.0),
            "incentive_cost": float(state.get("planned_incentive_cost") or 0.0),
            "next_step": "persist_decision",
            "error": None,
        }

    raise RecoveryWorkflowError(
        "LangGraph requires a persisted portfolio-selected action; it does not re-decide."
    )


def persist_decision(state: RecoveryWorkflowState) -> dict:
    payment_id = int(state["payment_id"])
    selected_action = state.get("selected_action")
    if selected_action is None:
        raise RecoveryWorkflowError("No recovery action was selected.")

    with SessionLocal() as db:
        try:
            payment = db.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                raise RecoveryWorkflowError(f"Payment {payment_id} was not found.")

            model_version = f"phase27-assignment-{state['optimization_assignment_id']}"
            existing = db.scalar(
                select(RecoveryDecisionModel)
                .where(
                    RecoveryDecisionModel.payment_id == payment_id,
                    RecoveryDecisionModel.selected_action
                    == RecoveryAction(selected_action),
                    RecoveryDecisionModel.model_version
                    == model_version,
                )
                .order_by(RecoveryDecisionModel.id.desc())
            )
            if existing is not None:
                return {
                    "decision_id": existing.id,
                    "next_step": (
                        "finalize"
                        if selected_action == RecoveryAction.DO_NOTHING.value
                        else "create_intervention"
                    ),
                }

            decision = RecoveryDecisionModel(
                payment_id=payment_id,
                selected_action=RecoveryAction(selected_action),
                predicted_probability=float(
                    state.get("predicted_probability") or 0.0
                ),
                expected_value=Decimal(str(state.get("expected_value") or 0.0)),
                policy_status=PolicyStatus(
                    state.get("policy_status") or PolicyStatus.ALLOWED.value
                ),
                model_version=model_version,
            )
            db.add(decision)
            db.commit()

            return {
                "decision_id": decision.id,
                "next_step": (
                    "finalize"
                    if selected_action == RecoveryAction.DO_NOTHING.value
                    else "create_intervention"
                ),
            }
        except Exception:
            db.rollback()
            raise


def create_intervention(state: RecoveryWorkflowState) -> dict:
    decision_id = state.get("decision_id")
    selected_action = state.get("selected_action")
    if decision_id is None or selected_action is None:
        raise RecoveryWorkflowError("Persisted decision is required.")

    with SessionLocal() as db:
        try:
            decision = db.get(
                RecoveryDecisionModel,
                decision_id,
                with_for_update=True,
            )
            if decision is None:
                raise RecoveryWorkflowError(
                    f"RecoveryDecision {decision_id} was not found."
                )

            existing = db.scalar(
                select(Intervention)
                .where(
                    Intervention.decision_id == decision_id,
                    Intervention.action_type == RecoveryAction(selected_action),
                )
                .order_by(Intervention.id.desc())
            )
            if existing is not None:
                return {
                    "intervention_id": existing.id,
                    "execution_status": existing.status.value,
                    "provider": existing.provider,
                    "provider_action_id": existing.provider_action_id,
                    "provider_status": existing.provider_status,
                    "next_step": (
                        "finalize"
                        if existing.status
                        in {InterventionStatus.EXECUTED, InterventionStatus.SUCCEEDED}
                        else "execute_intervention"
                    ),
                }

            intervention = Intervention(
                decision_id=decision_id,
                action_type=RecoveryAction(selected_action),
                status=InterventionStatus.PLANNED,
                intervention_cost=Decimal(
                    str(state.get("intervention_cost", 0.0))
                ),
                incentive_cost=Decimal(str(state.get("incentive_cost", 0.0))),
            )
            db.add(intervention)
            db.commit()

            return {
                "intervention_id": intervention.id,
                "execution_status": InterventionStatus.PLANNED.value,
                "next_step": "execute_intervention",
            }
        except Exception:
            db.rollback()
            raise


def execute_intervention(state: RecoveryWorkflowState) -> dict:
    intervention_id = state.get("intervention_id")
    selected_action = state.get("selected_action")
    if intervention_id is None or selected_action is None:
        raise RecoveryWorkflowError("Intervention is required before execution.")

    if selected_action != RecoveryAction.PAYMENT_LINK.value:
        return {
            "execution_status": InterventionStatus.PLANNED.value,
            "next_step": "finalize",
            "error": None,
        }

    with SessionLocal() as db:
        intervention = db.scalar(
            select(Intervention)
            .options(
                joinedload(Intervention.decision)
                .joinedload(RecoveryDecisionModel.payment)
            )
            .where(Intervention.id == intervention_id)
        )
        if intervention is None:
            raise RecoveryWorkflowError(
                f"Intervention {intervention_id} was not found."
            )
        payment = intervention.decision.payment
        original_payment_id = (
            payment.razorpay_payment_id or f"recoveriq_payment_{payment.id}"
        )
        amount = float(payment.amount)

    try:
        result = asyncio.run(
            get_recovery_service().execute_payment_link(
                original_payment_id=original_payment_id,
                amount=amount,
                idempotency_key=f"optimization-assignment-{state['optimization_assignment_id']}",
            )
        )
    except Exception as exc:
        with SessionLocal() as db:
            intervention = db.get(Intervention, intervention_id)
            if intervention is not None:
                intervention.status = InterventionStatus.FAILED
                db.commit()
        return {
            "execution_status": InterventionStatus.FAILED.value,
            "error": str(exc),
            "next_step": "handle_failure",
        }

    with SessionLocal() as db:
        try:
            intervention = db.get(
                Intervention,
                intervention_id,
                with_for_update=True,
            )
            if intervention is None:
                raise RecoveryWorkflowError(
                    f"Intervention {intervention_id} was not found."
                )

            if result.success and result.provider_action_id:
                intervention.provider = result.provider
                intervention.provider_action_id = result.provider_action_id
                intervention.provider_status = result.status
                intervention.status = InterventionStatus.EXECUTED
                intervention.executed_at = datetime.now(timezone.utc)
                db.commit()

                return {
                    "execution_status": InterventionStatus.EXECUTED.value,
                    "provider": result.provider,
                    "provider_action_id": result.provider_action_id,
                    "provider_status": result.status,
                    "payment_url": result.payment_url,
                    "error": None,
                    "next_step": "finalize",
                }

            intervention.status = InterventionStatus.FAILED
            db.commit()
            return {
                "execution_status": InterventionStatus.FAILED.value,
                "error": (
                    "RecoveryService returned no provider action ID."
                    if result.success
                    else "RecoveryService reported unsuccessful execution."
                ),
                "next_step": "handle_failure",
            }
        except Exception:
            db.rollback()
            raise


def handle_failure(state: RecoveryWorkflowState) -> dict:
    previous_retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 2))
    retry_count = previous_retry_count + 1

    return {
        "retry_count": retry_count,
        "next_step": (
            "execute_intervention"
            if previous_retry_count < max_retries
            else "finalize"
        ),
    }


def finalize(state: RecoveryWorkflowState) -> dict:
    execution_status = state.get("execution_status")
    if state.get("selected_action") == RecoveryAction.DO_NOTHING.value:
        execution_status = "DO_NOTHING"

    return {
        "execution_status": execution_status,
        "next_step": "END",
    }
