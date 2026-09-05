from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.decision.baseline import choose_baseline_action
from app.decision.decision_engine import DecisionEngine, RecoveryDecision
from app.decision.economic_value import calculate_economic_value
from app.optimizer.portfolio_optimizer import (
    CUSTOMER_CONTACT_ACTIONS,
    RETRY_ACTIONS,
    PortfolioConstraints,
    PortfolioOptimizer,
    PortfolioPayment,
)
from app.policies.engine import PolicyConfig
from app.schemas.optimization import (
    ActionAllocation,
    AlternativeScore,
    OptimizationConstraintsRequest,
    OptimizationRunResponse,
    PlanAssignment,
    PortfolioMetadataResponse,
    ResourceUsage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_DATA = PROJECT_ROOT / "data" / "processed" / "test.csv"
DEMO_SIZE = 1000
SOURCE = "FROZEN_DEMO_PORTFOLIO"
LABEL = "Demo Portfolio — 1,000 frozen held-out payments"
DEFAULTS = OptimizationConstraintsRequest()
POLICY = PolicyConfig(
    max_retry_attempts=3,
    max_customer_contacts=3,
    incentives_enabled=True,
    human_escalation_enabled=True,
    max_incentive_amount=500.0,
    min_amount_for_human_escalation=1000.0,
)
_latest_optimization_summary: dict | None = None
_latest_assignment_lookup: dict[str, dict] = {}


@dataclass(frozen=True)
class ScoredPortfolio:
    frame: pd.DataFrame
    payments: tuple[PortfolioPayment, ...]
    decisions: dict[str, RecoveryDecision]


def _context(row: pd.Series) -> dict:
    return {
        "amount": float(row["amount"]),
        "payment_method": str(row["payment_method"]),
        "failure_code": str(row["failure_code"]),
        "failure_type": str(row["failure_type"]),
        "attempt_number": int(row["attempt_number"]),
        "hour": int(row["hour"]),
        "day_of_week": int(row["day_of_week"]),
        "customer_tenure_days": int(row["customer_tenure_days"]),
        "successful_payments": int(row["successful_payments"]),
        "failed_payments": int(row["failed_payments"]),
        "previous_recoveries": int(row["previous_recoveries"]),
        "historical_recovery_rate": float(row["historical_recovery_rate"]),
        "avg_transaction_value": float(row["avg_transaction_value"]),
        "whatsapp_response_rate": float(row["whatsapp_response_rate"]),
        "email_response_rate": float(row["email_response_rate"]),
        "retry_success_rate": float(row["retry_success_rate"]),
        "payment_link_conversion_rate": float(row["payment_link_conversion_rate"]),
        "price_sensitivity": float(row["price_sensitivity"]),
        "customer_contact_count": 0,
    }


@lru_cache(maxsize=1)
def scored_demo_portfolio() -> ScoredPortfolio:
    if not TEST_DATA.is_file():
        raise RuntimeError(f"Frozen demo portfolio is missing: {TEST_DATA}")
    frame = pd.read_csv(TEST_DATA, nrows=DEMO_SIZE)
    contexts = [_context(row) for _, row in frame.iterrows()]
    ids = [str(value) for value in frame["payment_id"]]
    engine = DecisionEngine()
    predictions = engine.action_evaluator.evaluate_batch(contexts)
    decisions = {}
    for payment_id, context, prediction_set in zip(ids, contexts, predictions):
        control = next(
            item.recovery_probability
            for item in prediction_set
            if item.action == "DO_NOTHING"
        )
        values = [
            calculate_economic_value(
                action=item.action,
                recovery_probability=item.recovery_probability,
                estimated_uplift=(
                    0.0
                    if item.action == "DO_NOTHING"
                    else item.recovery_probability - control
                ),
                amount=float(context["amount"]),
            )
            for item in prediction_set
        ]
        allowed, policy_decisions = engine.policy_engine.filter_actions(
            actions=[value.action for value in values],
            context=context,
            policy=POLICY,
        )
        ranked = sorted(
            (value for value in values if value.action in set(allowed)),
            key=lambda value: value.incremental_value,
            reverse=True,
        )
        best = ranked[0]
        decisions[payment_id] = RecoveryDecision(
            recommended_action=best.action,
            recovery_probability=best.recovery_probability,
            expected_net_value=best.expected_net_value,
            incremental_value=best.incremental_value,
            ranked_actions=ranked,
            policy_decisions=policy_decisions,
        )
    payments = tuple(
        PortfolioPayment(payment_id=payment_id, context=context)
        for payment_id, context in zip(ids, contexts)
    )
    return ScoredPortfolio(frame=frame, payments=payments, decisions=decisions)


def portfolio_metadata() -> PortfolioMetadataResponse:
    frame = pd.read_csv(TEST_DATA, usecols=["amount"], nrows=DEMO_SIZE)
    return PortfolioMetadataResponse(
        source=SOURCE,
        label=LABEL,
        payment_count=len(frame),
        revenue_at_risk=float(frame["amount"].sum()),
        default_constraints=DEFAULTS,
    )


def run_optimization(request: OptimizationConstraintsRequest) -> OptimizationRunResponse:
    global _latest_optimization_summary, _latest_assignment_lookup
    scored = scored_demo_portfolio()
    constraints = PortfolioConstraints(
        max_total_intervention_spend=request.total_budget,
        max_incentive_spend=request.incentive_budget,
        max_retry_actions=request.max_retries,
        max_customer_contacts=request.max_contacts,
        max_whatsapp_actions=request.max_whatsapp,
        max_incentive_actions=request.max_incentive_actions,
        max_human_escalations=request.max_human_escalations,
        solver_time_limit_ms=request.solver_timeout_ms,
    )
    result = PortfolioOptimizer().optimize(
        payments=list(scored.payments),
        constraints=constraints,
        policy=POLICY,
        precomputed_decisions=scored.decisions,
    )
    rows = {str(row["payment_id"]): row for _, row in scored.frame.iterrows()}
    assignments = []
    allocation_values: dict[str, float] = defaultdict(float)
    probability_total = 0.0
    baseline_net = 0.0
    baseline_probability = 0.0
    for payment in scored.payments:
        decision = scored.decisions[payment.payment_id]
        baseline_action = choose_baseline_action(
            failure_type=str(payment.context["failure_type"]),
            attempt_number=int(payment.context["attempt_number"]),
        ).action
        values = {value.action: value for value in decision.ranked_actions}
        baseline_value = values.get(baseline_action, values["DO_NOTHING"])
        baseline_net += baseline_value.expected_net_value
        baseline_probability += baseline_value.recovery_probability

    for assignment in result.assignments:
        row = rows[assignment.payment_id]
        decision = scored.decisions[assignment.payment_id]
        alternatives = sorted(
            decision.ranked_actions,
            key=lambda value: value.incremental_value,
            reverse=True,
        )
        allocation_values[assignment.action] += assignment.incremental_value
        probability_total += assignment.recovery_probability
        assignments.append(
            PlanAssignment(
                payment_id=assignment.payment_id,
                amount=float(row["amount"]),
                payment_method=str(row["payment_method"]),
                failure_type=str(row["failure_type"]),
                action=assignment.action,
                recovery_probability=assignment.recovery_probability,
                incremental_value=assignment.incremental_value,
                intervention_cost=assignment.intervention_cost,
                incentive_cost=assignment.incentive_cost,
                expected_net_value=assignment.expected_net_value,
                policy_status="ALLOWED",
                alternatives=[
                    AlternativeScore(
                        action=value.action,
                        recovery_probability=value.recovery_probability,
                        incremental_value=value.incremental_value,
                        intervention_cost=value.intervention_cost,
                        expected_net_value=value.expected_net_value,
                    )
                    for value in alternatives
                ],
            )
        )

    count = len(assignments)
    improvement = result.total_expected_net_value - baseline_net
    action_allocation = [
        ActionAllocation(
            action=action,
            count=result.action_counts.get(action, 0),
            percentage=result.action_counts.get(action, 0) / count * 100,
            incremental_value=allocation_values[action],
        )
        for action in [
            "RETRY_NOW", "RETRY_LATER", "PAYMENT_LINK", "ALTERNATE_METHOD",
            "WHATSAPP", "EMAIL", "INCENTIVE", "HUMAN_ESCALATION", "DO_NOTHING",
        ]
    ]
    human_count = result.action_counts.get("HUMAN_ESCALATION", 0)
    whatsapp_count = result.action_counts.get("WHATSAPP", 0)
    incentive_count = result.action_counts.get("INCENTIVE", 0)
    usages = [
        ("spend", "Recovery spend", result.total_intervention_spend, request.total_budget, "INR"),
        ("retries", "Retries", result.retry_count, request.max_retries, "count"),
        ("contacts", "Customer contacts", result.customer_contact_count, request.max_contacts, "count"),
        ("whatsapp", "WhatsApp", whatsapp_count, request.max_whatsapp, "count"),
        ("incentive_spend", "Incentive spend", result.total_incentive_spend, request.incentive_budget, "INR"),
        ("incentives", "Incentive actions", incentive_count, request.max_incentive_actions, "count"),
        ("human", "Human escalations", human_count, request.max_human_escalations, "count"),
    ]
    response = OptimizationRunResponse(
        portfolio_source=SOURCE,
        portfolio_label=LABEL,
        status=result.status,
        payment_count=count,
        revenue_at_risk=float(scored.frame["amount"].sum()),
        baseline_net_value=baseline_net,
        baseline_recovery_rate=baseline_probability / count * 100,
        optimized_net_value=result.total_expected_net_value,
        total_incremental_value=result.total_incremental_value,
        improvement_amount=improvement,
        improvement_percent=(improvement / baseline_net * 100 if baseline_net else 0),
        expected_recovery_rate=probability_total / count * 100,
        intervention_spend=result.total_intervention_spend,
        action_allocation=action_allocation,
        resource_usage=[ResourceUsage(key=key,label=label,used=float(used),limit=float(limit),unit=unit,within_constraint=float(used)<=float(limit)+1e-6) for key,label,used,limit,unit in usages],
        assignments=assignments,
    )
    _latest_optimization_summary = {
        "source": SOURCE,
        "status": response.status,
        "payment_count": response.payment_count,
        "total_incremental_value": round(response.total_incremental_value, 2),
        "expected_recovery_rate": round(response.expected_recovery_rate, 2),
        "action_allocation": [
            {"action": item.action, "count": item.count}
            for item in response.action_allocation
        ],
        "resource_usage": [
            {
                "label": item.label,
                "used": round(item.used, 2),
                "limit": round(item.limit, 2),
                "unit": item.unit,
                "within_constraint": item.within_constraint,
            }
            for item in response.resource_usage
        ],
    }
    _latest_assignment_lookup = {
        item.payment_id: item.model_dump(mode="json")
        for item in response.assignments
    }
    return response


def get_latest_optimization_summary() -> dict | None:
    return _latest_optimization_summary


def get_latest_optimization_assignment(payment_id: str) -> dict | None:
    return _latest_assignment_lookup.get(payment_id)
