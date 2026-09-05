from __future__ import annotations

from datetime import datetime, timezone
from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.celery_app import celery_app
from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.models.enums import PaymentStatus, PolicyStatus
from app.models.recovery_batch import OptimizationAssignment
from app.orchestration.recovery_graph import run_recovery_workflow
from app.schemas.optimization import OptimizationConstraintsRequest
from app.services.recovery_batch_service import plan_batch
from app.services.batch_event_service import BatchStatusEvent, publish_assignment_state, publish_batch_event

TERMINAL_ASSIGNMENT_STATUSES = {"RECOVERED", "AWAITING_PAYMENT", "NO_ACTION", "MANUAL_REQUIRED", "APPROVAL_REQUIRED", "POLICY_REJECTED", "SKIPPED"}


@celery_app.task(bind=True, name="app.tasks.batch_tasks.plan_recovery_batch", max_retries=2)
def plan_recovery_batch_task(self: Task, batch_id: int, constraints: dict) -> dict:
    with SessionLocal() as db:
        try:
            plan = plan_batch(db, batch_id, OptimizationConstraintsRequest.model_validate(constraints))
            assignment_count = db.query(OptimizationAssignment).filter_by(plan_id=plan.id).count()
            publish_batch_event(BatchStatusEvent(type="batch.updated", batch_id=batch_id, status="READY"))
            return {"batch_id": batch_id, "plan_id": plan.id, "status": "READY", "assignment_count": assignment_count}
        except (LookupError, ValueError):
            raise
        except Exception as exc:
            raise self.retry(exc=exc, countdown=2 ** min(self.request.retries, 2))


@celery_app.task(bind=True, name="app.tasks.batch_tasks.execute_recovery_assignment", max_retries=3)
def execute_recovery_assignment_task(self: Task, assignment_id: int) -> dict:
    db = SessionLocal()
    try:
        assignment = db.scalar(select(OptimizationAssignment).options(joinedload(OptimizationAssignment.payment), joinedload(OptimizationAssignment.plan)).where(OptimizationAssignment.id == assignment_id).with_for_update(of=OptimizationAssignment))
        if assignment is None:
            raise LookupError(f"OptimizationAssignment {assignment_id} was not found.")
        if assignment.execution_status in TERMINAL_ASSIGNMENT_STATUSES:
            return {"assignment_id": assignment_id, "status": assignment.execution_status, "skipped": True}
        payment = assignment.payment
        if payment.status is not PaymentStatus.FAILED:
            assignment.execution_status = "RECOVERED" if payment.status is PaymentStatus.RECOVERED else "SKIPPED"
            db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment_id, "status": assignment.execution_status}
        if assignment.policy_status is PolicyStatus.REJECTED:
            assignment.execution_status = "POLICY_REJECTED"; db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment_id, "status": assignment.execution_status}
        if assignment.policy_status is PolicyStatus.REQUIRES_APPROVAL:
            assignment.execution_status = "APPROVAL_REQUIRED"; db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment_id, "status": assignment.execution_status}
        if assignment.selected_action is RecoveryAction.DO_NOTHING:
            assignment.execution_status = "NO_ACTION"; db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment_id, "status": assignment.execution_status}
        if assignment.selected_action is not RecoveryAction.PAYMENT_LINK:
            assignment.execution_status = "MANUAL_REQUIRED"; db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment_id, "status": assignment.execution_status}
        assignment.execution_status = "EXECUTING"; db.flush()
        db.commit(); publish_assignment_state(db, assignment)
        state = run_recovery_workflow(payment_id=payment.id, planned_action=assignment.selected_action.value, optimization_assignment_id=assignment.id, recovery_batch_id=assignment.plan.batch_id, planned_policy_status=assignment.policy_status.value, planned_probability=assignment.recovery_probability, planned_expected_value=float(assignment.expected_value), planned_incremental_value=float(assignment.incremental_value), planned_intervention_cost=float(assignment.intervention_cost), planned_incentive_cost=float(assignment.incentive_cost))
        assignment.decision_id = state.get("decision_id"); assignment.intervention_id = state.get("intervention_id"); assignment.provider = state.get("provider"); assignment.provider_action_id = state.get("provider_action_id"); assignment.provider_status = state.get("provider_status"); assignment.payment_url = state.get("payment_url"); assignment.error_message = state.get("error"); assignment.executed_at = datetime.now(timezone.utc)
        assignment.execution_status = "AWAITING_PAYMENT" if state.get("execution_status") == "EXECUTED" else "FAILED"
        db.commit(); publish_assignment_state(db, assignment); return {"assignment_id": assignment.id, "status": assignment.execution_status, "provider_action_id": assignment.provider_action_id}
    except (LookupError, ValueError):
        db.rollback(); raise
    except Exception as exc:
        db.rollback()
        failed = db.get(OptimizationAssignment, assignment_id)
        if failed is not None:
            failed.execution_status = "FAILED"; failed.error_message = str(exc)[:1000]; db.commit(); publish_assignment_state(db, failed)
        raise self.retry(exc=exc, countdown=2 ** min(self.request.retries, 3))
    finally:
        db.close()
