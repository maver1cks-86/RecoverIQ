from __future__ import annotations

import random
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.decision.decision_engine import DecisionEngine, RecoveryDecision
from app.decision.actions import RecoveryAction
from app.decision.economic_value import calculate_economic_value
from app.models.customer import Customer
from app.models.enums import PaymentStatus, PolicyStatus
from app.models.merchant import Merchant
from app.models.payment import Payment
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch, RecoveryBatchPayment
from app.optimizer.portfolio_optimizer import PortfolioConstraints, PortfolioOptimizer, PortfolioPayment
from app.orchestration.nodes import _build_context
from app.policies.engine import PolicyConfig
from app.schemas.optimization import OptimizationConstraintsRequest
from app.services.revenue_risk_service import RevenueRiskService

SOURCE = "DEMO_SYNTHETIC_FAILED_PAYMENTS"
MODEL_VERSION = "phase27-db-batch-v1"
POLICY = PolicyConfig()
ACTIVE_EXECUTION_STATUSES = {"PLANNED", "QUEUED", "EXECUTING"}
DEMO_PAYMENT_CREATED_AT = datetime(2025, 1, 6, 10, 0, tzinfo=timezone.utc)


def create_demo_batch(db: Session, payment_count: int, reference_id: str | None = None) -> RecoveryBatch:
    reference = reference_id or f"phase27-demo-{uuid4().hex}"
    existing = db.scalar(select(RecoveryBatch).where(RecoveryBatch.reference_id == reference))
    if existing is not None:
        return existing
    rng = random.Random(2700 + payment_count)
    merchant = Merchant(name=f"RecoverIQ Recovery Batch {reference[-8:]}")
    db.add(merchant); db.flush()
    batch = RecoveryBatch(merchant_id=merchant.id, source=SOURCE, reference_id=reference, status="CREATED", payment_count=payment_count, revenue_at_risk=Decimal("0.00"))
    db.add(batch); db.flush()
    failure_types = ["PAYMENT_METHOD_ISSUE", "TEMPORARY_BANK_FAILURE", "CUSTOMER_ACTION_REQUIRED", "INSUFFICIENT_FUNDS", "NETWORK_FAILURE", "HARD_DECLINE"]
    total = Decimal("0.00")
    customer_created_at = datetime.now(timezone.utc)
    for index in range(payment_count):
        customer = Customer(merchant_id=merchant.id, external_customer_id=f"{reference}-customer-{index}", successful_payments=rng.randint(0, 15), failed_payments=rng.randint(1, 6), previous_recoveries=rng.randint(0, 3), avg_transaction_value=Decimal(str(rng.randint(200, 4000))), created_at=customer_created_at)
        db.add(customer); db.flush()
        amount = Decimal(str(rng.randint(1000, 150000) / 100)).quantize(Decimal("0.01"))
        failure = failure_types[index % len(failure_types)]
        payment = Payment(merchant_id=merchant.id, customer_id=customer.id, razorpay_payment_id=f"pay_demo_{uuid4().hex}", amount=amount, currency="INR", payment_method=["card", "upi", "netbanking"][index % 3], status=PaymentStatus.FAILED, failure_code=failure, failure_reason=f"Demo {failure.lower().replace('_', ' ')}", attempt_count=1 + index % 2, created_at=DEMO_PAYMENT_CREATED_AT)
        db.add(payment); db.flush(); db.add(RecoveryBatchPayment(batch_id=batch.id, payment_id=payment.id)); total += amount
    batch.revenue_at_risk = total
    db.commit(); db.refresh(batch)
    return batch


def _portfolio_constraints(request: OptimizationConstraintsRequest) -> PortfolioConstraints:
    enabled_actions = (
        None
        if request.enabled_actions is None
        else frozenset(action.value for action in request.enabled_actions)
    )
    return PortfolioConstraints(max_total_intervention_spend=request.total_budget, max_incentive_spend=request.incentive_budget, max_retry_actions=request.max_retries, max_customer_contacts=request.max_contacts, max_whatsapp_actions=request.max_whatsapp, max_incentive_actions=request.max_incentive_actions, max_human_escalations=request.max_human_escalations, enabled_actions=enabled_actions, solver_time_limit_ms=request.solver_timeout_ms)


def plan_batch(db: Session, batch_id: int, request: OptimizationConstraintsRequest) -> OptimizationPlan:
    batch = db.get(RecoveryBatch, batch_id, with_for_update=True)
    if batch is None: raise LookupError(f"RecoveryBatch {batch_id} was not found.")
    snapshot = request.model_dump(mode="json")
    current_plan = latest_plan(db, batch_id)
    if current_plan is not None and current_plan.constraints_snapshot == snapshot:
        if batch.status != "READY":
            batch.status = "READY"
            db.commit()
        return current_plan
    if batch.execution_started_at is not None:
        raise ValueError("An execution-started batch cannot be replanned.")
    if batch.status not in {"CREATED", "QUEUED", "FAILED", "READY"}: raise ValueError(f"Batch cannot be planned from status {batch.status}.")
    batch.status = "SCORING"; batch.planning_started_at = datetime.now(timezone.utc); batch.error_message = None; db.commit()
    try:
        members = db.scalars(select(RecoveryBatchPayment).options(joinedload(RecoveryBatchPayment.payment).joinedload(Payment.customer)).where(RecoveryBatchPayment.batch_id == batch_id).order_by(RecoveryBatchPayment.id)).all()
        eligible = [member.payment for member in members if RevenueRiskService.is_at_risk(member.payment)]
        if not eligible: raise ValueError("Batch contains no eligible FAILED payments.")
        contexts = [_build_context(payment) for payment in eligible]
        engine = DecisionEngine(); prediction_sets = engine.action_evaluator.evaluate_batch(contexts)
        decisions: dict[str, RecoveryDecision] = {}
        operational_actions = (
            None
            if request.enabled_actions is None
            else {action.value for action in request.enabled_actions}
        )
        for payment, context, predictions in zip(eligible, contexts, prediction_sets):
            control = next(item.recovery_probability for item in predictions if item.action == "DO_NOTHING")
            values = [calculate_economic_value(action=item.action, recovery_probability=item.recovery_probability, estimated_uplift=0.0 if item.action == "DO_NOTHING" else item.recovery_probability-control, amount=float(payment.amount)) for item in predictions]
            allowed, policy_decisions = engine.policy_engine.filter_actions([value.action for value in values], context, POLICY)
            allowed_set = set(allowed)
            if operational_actions is not None:
                allowed_set &= operational_actions
            ranked = sorted((value for value in values if value.action in allowed_set), key=lambda value: value.incremental_value, reverse=True)
            if not ranked or RecoveryAction.DO_NOTHING.value not in allowed_set:
                raise ValueError("DO_NOTHING must remain in the feasible action set.")
            best = ranked[0]
            decisions[str(payment.id)] = RecoveryDecision(best.action, best.recovery_probability, best.expected_net_value, best.incremental_value, ranked, policy_decisions)
        batch.status = "OPTIMIZING"; db.commit()
        result = PortfolioOptimizer().optimize([PortfolioPayment(str(payment.id), context) for payment, context in zip(eligible, contexts)], _portfolio_constraints(request), POLICY, decisions)
        usages = [{"key":"spend","used":result.total_intervention_spend,"limit":request.total_budget},{"key":"retries","used":result.retry_count,"limit":request.max_retries},{"key":"contacts","used":result.customer_contact_count,"limit":request.max_contacts},{"key":"whatsapp","used":result.action_counts.get("WHATSAPP",0),"limit":request.max_whatsapp},{"key":"incentives","used":result.action_counts.get("INCENTIVE",0),"limit":request.max_incentive_actions},{"key":"human","used":result.action_counts.get("HUMAN_ESCALATION",0),"limit":request.max_human_escalations}]
        next_version = 1 if current_plan is None else current_plan.version + 1
        plan = OptimizationPlan(batch_id=batch_id, version=next_version, solver_status=result.status, objective_value=Decimal(str(result.total_incremental_value)), expected_net_value=Decimal(str(result.total_expected_net_value)), constraints_snapshot=snapshot, resource_usage=usages, model_version=MODEL_VERSION)
        db.add(plan); db.flush()
        for item in result.assignments:
            ranked = decisions[item.payment_id].ranked_actions
            selected_rank = next(index for index, value in enumerate(ranked, 1) if value.action == item.action)
            alternatives = [
                {
                    "action": value.action,
                    "recovery_probability": value.recovery_probability,
                    "expected_value": value.expected_net_value,
                    "incremental_value": value.incremental_value,
                    "intervention_cost": value.intervention_cost,
                    "incentive_cost": value.incentive_cost,
                    "rank": index,
                }
                for index, value in enumerate(ranked, 1)
            ]
            standalone_best = ranked[0].action
            policy_evidence = [
                {
                    "action": decision.action,
                    "status": (
                        "OPERATIONALLY_DISABLED"
                        if operational_actions is not None
                        and decision.action not in operational_actions
                        else
                        "REQUIRES_APPROVAL"
                        if decision.requires_approval
                        else "ALLOWED" if decision.allowed else "REJECTED"
                    ),
                    "reason": (
                        "Action is not enabled for this merchant/platform plan."
                        if operational_actions is not None
                        and decision.action not in operational_actions
                        else decision.reason
                    ),
                }
                for decision in decisions[item.payment_id].policy_decisions
            ]
            selected_policy = next(
                decision
                for decision in decisions[item.payment_id].policy_decisions
                if decision.action == item.action
            )
            selected_policy_status = (
                PolicyStatus.REQUIRES_APPROVAL
                if selected_policy.requires_approval
                else PolicyStatus.ALLOWED
            )
            db.add(OptimizationAssignment(plan_id=plan.id, payment_id=int(item.payment_id), selected_action=item.action, policy_status=selected_policy_status, recovery_probability=item.recovery_probability, expected_value=Decimal(str(item.expected_net_value)), incremental_value=Decimal(str(item.incremental_value)), intervention_cost=Decimal(str(item.intervention_cost)), incentive_cost=Decimal(str(item.incentive_cost)), execution_status="PLANNED", standalone_best_action=standalone_best, selected_rank=selected_rank, portfolio_agreement=item.action == standalone_best, alternatives=alternatives, policy_evidence=policy_evidence))
        batch.status = "READY"; batch.planning_completed_at = datetime.now(timezone.utc); db.commit(); db.refresh(plan); return plan
    except Exception as exc:
        db.rollback(); batch = db.get(RecoveryBatch, batch_id); batch.status = "FAILED"; batch.error_message = str(exc)[:1000]; db.commit(); raise


def latest_plan(db: Session, batch_id: int) -> OptimizationPlan | None:
    return db.scalar(select(OptimizationPlan).where(OptimizationPlan.batch_id == batch_id).order_by(OptimizationPlan.id.desc()))


def reconcile_batch_execution(db: Session, batch: RecoveryBatch) -> RecoveryBatch:
    if batch.status != "EXECUTING":
        return batch
    plan = latest_plan(db, batch.id)
    if plan is None:
        return batch
    active = db.scalar(
        select(func.count(OptimizationAssignment.id)).where(
            OptimizationAssignment.plan_id == plan.id,
            OptimizationAssignment.execution_status.in_(ACTIVE_EXECUTION_STATUSES),
        )
    )
    if not active:
        batch.status = "COMPLETED"
        batch.execution_completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)
    return batch


def batch_summary(db: Session, batch_id: int) -> dict:
    batch = db.get(RecoveryBatch, batch_id)
    if batch is None: raise LookupError
    reconcile_batch_execution(db, batch)
    plan = latest_plan(db, batch_id)
    assignments = [] if plan is None else db.scalars(select(OptimizationAssignment).options(joinedload(OptimizationAssignment.intervention)).where(OptimizationAssignment.plan_id == plan.id)).all()
    action_counts = Counter(item.selected_action.value for item in assignments); execution_counts = Counter(item.execution_status for item in assignments)
    recovered = Decimal("0.00")
    for item in assignments:
        if item.intervention_id:
            from app.models.outcome import Outcome
            outcome = db.scalar(select(Outcome).where(Outcome.intervention_id == item.intervention_id, Outcome.recovered.is_(True)))
            if outcome: recovered += outcome.recovered_amount
    return {"batch": batch, "plan": plan, "observed_recovered_amount": recovered, "estimated_incremental_value": plan.objective_value if plan else Decimal("0.00"), "action_allocation": dict(action_counts), "execution_counts": dict(execution_counts), "constraint_utilization": plan.resource_usage if plan else [], "constraints_snapshot": plan.constraints_snapshot if plan else {}}
