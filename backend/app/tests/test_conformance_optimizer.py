from __future__ import annotations

import numpy as np

from app.decision.decision_engine import RecoveryDecision
from app.decision.economic_value import EconomicValue, calculate_economic_value
from app.ml.features import LEAKAGE_COLUMNS, MODEL_FEATURES
from app.ml.recovery_predictor import RecoveryPredictor
from app.optimizer.portfolio_optimizer import (
    PortfolioConstraints,
    PortfolioOptimizer,
    PortfolioPayment,
)
from app.policies.engine import PolicyConfig, PolicyDecision, PolicyEngine


def value(action: str, incremental: float, cost: float = 0.0) -> EconomicValue:
    return EconomicValue(
        action=action,
        recovery_probability=0.5,
        estimated_uplift=0.1,
        intervention_cost=cost,
        incentive_cost=cost if action == "INCENTIVE" else 0.0,
        expected_gross_value=50.0,
        expected_net_value=50.0 - cost,
        incremental_value=incremental,
    )


def decision(*values: EconomicValue, rejected: tuple[str, ...] = ()) -> RecoveryDecision:
    ranked = list(values)
    return RecoveryDecision(
        recommended_action=ranked[0].action,
        recovery_probability=ranked[0].recovery_probability,
        expected_net_value=ranked[0].expected_net_value,
        incremental_value=ranked[0].incremental_value,
        ranked_actions=ranked,
        policy_decisions=[
            PolicyDecision(item.action, True, "allowed") for item in ranked
        ] + [PolicyDecision(action, False, "rejected") for action in rejected],
    )


def solve(decisions: dict[str, RecoveryDecision], **limits):
    payments = [PortfolioPayment(payment_id, {}) for payment_id in decisions]
    return PortfolioOptimizer().optimize(
        payments,
        PortfolioConstraints(**limits),
        precomputed_decisions=decisions,
    )


def rank_for(item, decisions: dict[str, RecoveryDecision]) -> int:
    return next(
        index
        for index, candidate in enumerate(decisions[item.payment_id].ranked_actions, 1)
        if candidate.action == item.action
    )


def test_global_incentive_cap_forces_true_lower_rank_tradeoff() -> None:
    decisions = {
        str(index): decision(
            value("INCENTIVE", 10 - index / 10, 1),
            value("ALTERNATE_METHOD", 6, 0.4),
            value("DO_NOTHING", 0),
        )
        for index in range(3)
    }
    result = solve(decisions, max_incentive_actions=1)
    assert len(result.assignments) == 3
    assert result.action_counts["INCENTIVE"] == 1
    assert any(rank_for(item, decisions) > 1 for item in result.assignments)


def test_global_retry_cap_forces_true_lower_rank_tradeoff() -> None:
    decisions = {
        str(index): decision(
            value("RETRY_LATER", 9 - index / 10, 0.3),
            value("ALTERNATE_METHOD", 5, 0.4),
            value("DO_NOTHING", 0),
        )
        for index in range(3)
    }
    result = solve(decisions, max_retry_actions=1)
    assert result.retry_count == 1
    assert any(rank_for(item, decisions) > 1 for item in result.assignments)


def test_global_contact_cap_forces_true_lower_rank_tradeoff() -> None:
    decisions = {
        str(index): decision(
            value("EMAIL", 8 - index / 10, 0.1),
            value("ALTERNATE_METHOD", 4, 0.4),
            value("DO_NOTHING", 0),
        )
        for index in range(3)
    }
    result = solve(decisions, max_customer_contacts=1)
    assert result.customer_contact_count == 1
    assert any(rank_for(item, decisions) > 1 for item in result.assignments)


def test_total_budget_forces_lower_rank_and_exhaustion_selects_do_nothing() -> None:
    decisions = {
        str(index): decision(
            value("HUMAN_ESCALATION", 10 - index, 5),
            value("EMAIL", 4, 0.1),
            value("DO_NOTHING", 0),
        )
        for index in range(2)
    }
    constrained = solve(decisions, max_total_intervention_spend=0.2)
    assert all(item.action == "EMAIL" for item in constrained.assignments)
    assert all(rank_for(item, decisions) == 2 for item in constrained.assignments)

    scarce = {
        str(index): decision(value("INCENTIVE", 10, 1), value("DO_NOTHING", 0))
        for index in range(2)
    }
    exhausted = solve(
        scarce,
        max_incentive_actions=0,
        max_incentive_spend=0,
        max_total_intervention_spend=0,
    )
    assert all(item.action == "DO_NOTHING" for item in exhausted.assignments)


def test_policy_rejected_action_is_not_a_milp_variable() -> None:
    decisions = {
        "1": decision(
            value("EMAIL", 2, 0.1),
            value("DO_NOTHING", 0),
            rejected=("INCENTIVE",),
        )
    }
    result = solve(decisions)
    assert result.assignments[0].action == "EMAIL"


def test_enabled_actions_define_operational_feasible_set() -> None:
    decisions = {
        "1": decision(
            value("INCENTIVE", 10, 1),
            value("PAYMENT_LINK", 5, 0.5),
            value("DO_NOTHING", 0),
        )
    }
    result = solve(
        decisions,
        enabled_actions=frozenset({"PAYMENT_LINK", "DO_NOTHING"}),
    )
    assert result.assignments[0].action == "PAYMENT_LINK"


def test_economics_can_prefer_lower_probability_after_cost() -> None:
    expensive = calculate_economic_value("HUMAN_ESCALATION", 0.90, 0.10, 100)
    efficient = calculate_economic_value("EMAIL", 0.50, 0.05, 100)
    assert expensive.recovery_probability > efficient.recovery_probability
    assert expensive.incremental_value < efficient.incremental_value


def test_live_model_input_is_action_conditioned_and_excludes_leakage() -> None:
    captured = []

    class FakeModel:
        def predict_proba(self, frame):
            captured.append(frame.copy())
            probabilities = frame["action_taken"].map(
                {"EMAIL": 0.2, "PAYMENT_LINK": 0.7}
            ).to_numpy()
            return np.column_stack([1 - probabilities, probabilities])

    predictor = object.__new__(RecoveryPredictor)
    predictor.model = FakeModel()
    context = {
        feature: 1.0 for feature in MODEL_FEATURES if feature != "action_taken"
    }
    for categorical in ("payment_method", "failure_code", "failure_type"):
        context[categorical] = "test"
    context.update({name: "leak" for name in LEAKAGE_COLUMNS})

    probabilities = predictor.predict_probabilities_batch(
        [context], ["EMAIL", "PAYMENT_LINK"]
    )
    assert probabilities == [[0.2, 0.7]]
    assert list(captured[0].columns) == MODEL_FEATURES
    assert not set(LEAKAGE_COLUMNS).intersection(captured[0].columns)


def test_policy_blocks_retries_contacts_and_marks_approval() -> None:
    engine = PolicyEngine()
    context = {
        "failure_type": "HARD_DECLINE",
        "attempt_number": 3,
        "customer_contact_count": 3,
        "amount": 2000,
    }
    policy = PolicyConfig(
        max_retry_attempts=3,
        max_customer_contacts=3,
        approval_required_actions={"INCENTIVE"},
    )
    assert not engine.evaluate_action("RETRY_NOW", context, policy).allowed
    assert not engine.evaluate_action("EMAIL", context, policy).allowed
    incentive = engine.evaluate_action(
        "INCENTIVE", {**context, "customer_contact_count": 0}, policy
    )
    assert incentive.allowed and incentive.requires_approval
    do_nothing = engine.evaluate_action("DO_NOTHING", context, policy)
    assert do_nothing.allowed and not do_nothing.requires_approval
