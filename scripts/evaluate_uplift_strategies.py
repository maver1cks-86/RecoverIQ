"""Compare baseline and uplift-aware strategies on the frozen test portfolio."""

from collections import Counter
import hashlib
import math
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(BACKEND_ROOT))

from app.decision.actions import RecoveryAction
from app.decision.decision_engine import DecisionEngine, RecoveryDecision
from app.optimizer.portfolio_optimizer import (
    CUSTOMER_CONTACT_ACTIONS,
    RETRY_ACTIONS,
    PortfolioConstraints,
    PortfolioOptimizationResult,
    PortfolioOptimizer,
    PortfolioPayment,
)
from scripts.evaluate_strategies import (
    POLICY,
    PORTFOLIO_CONSTRAINTS,
    TEST_PATH,
    aggregate_strategy,
    build_decision_context,
    evaluate_baseline,
    evaluate_ground_truth,
)


COMPARISON_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "uplift_strategy_comparison.csv"
)
ASSIGNMENTS_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "uplift_strategy_assignments.csv"
)
PHASE_17_OUTPUT_PATHS = [
    PROJECT_ROOT / "data" / "processed" / "strategy_comparison.csv",
    PROJECT_ROOT / "data" / "processed" / "strategy_assignments.csv",
]

EXPECTED_PAYMENTS = 10_000
CANONICAL_ACTIONS = {action.value for action in RecoveryAction}


def format_currency(value: float) -> str:
    """Use an ASCII currency label that is safe in Windows consoles."""
    return f"Rs. {value:,.2f}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_phase_17_hashes() -> dict[Path, str]:
    missing = [path for path in PHASE_17_OUTPUT_PATHS if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Frozen Phase 17 output is missing: "
            + ", ".join(str(path) for path in missing)
        )
    return {path: file_sha256(path) for path in PHASE_17_OUTPUT_PATHS}


def selected_economic_value(decision: RecoveryDecision, action: str):
    return next(
        (item for item in decision.ranked_actions if item.action == action),
        None,
    )


def build_precomputed_uplift_decisions(
    df: pd.DataFrame,
) -> tuple[dict[str, RecoveryDecision], dict[str, dict]]:
    print(f"Preparing {len(df):,} contexts...")
    payment_ids = [str(payment_id) for payment_id in df["payment_id"]]
    contexts = [build_decision_context(row) for _, row in df.iterrows()]

    engine = DecisionEngine()

    print("Running batched recovery prediction...")
    recovery_predictions = engine.action_evaluator.evaluate_batch(contexts)
    print("Recovery prediction complete.")

    print("Running batched uplift prediction...")
    uplift_predictions = engine.uplift_predictor.predict_all_uplifts_batch(
        contexts
    )
    print("Uplift prediction complete.")

    if not (
        len(payment_ids)
        == len(contexts)
        == len(recovery_predictions)
        == len(uplift_predictions)
    ):
        raise ValueError("Batched inference returned an unexpected number of rows")

    print("Applying economics and policy...")
    decisions = {}
    context_by_payment = {}

    for index, (
        payment_id,
        context,
        recovery_prediction_set,
        uplift_prediction_set,
    ) in enumerate(
        zip(
            payment_ids,
            contexts,
            recovery_predictions,
            uplift_predictions,
        ),
        start=1,
    ):
        decisions[payment_id] = engine.evaluate_from_predictions(
            context=context,
            predictions=recovery_prediction_set,
            uplift_predictions=uplift_prediction_set,
            policy=POLICY,
        )
        context_by_payment[payment_id] = context

        if index % 1_000 == 0:
            print(f"Decisions prepared: {index:,}/{len(df):,}")

    print(f"Precomputed {len(decisions):,} uplift-aware decisions.")
    return decisions, context_by_payment


def evaluate_uplift_decision_strategy(
    df: pd.DataFrame,
    precomputed_decisions: dict[str, RecoveryDecision],
) -> tuple[dict, list[dict]]:
    assignments = []

    for index, (_, row) in enumerate(df.iterrows(), start=1):
        payment_id = str(row["payment_id"])
        if payment_id not in precomputed_decisions:
            raise ValueError(f"Missing precomputed decision for payment {payment_id}")

        decision = precomputed_decisions[payment_id]
        action = decision.recommended_action
        selected_value = selected_economic_value(decision, action)
        if selected_value is None:
            raise ValueError(f"Selected value missing for payment {payment_id}")

        assignments.append(
            {
                "payment_id": payment_id,
                "strategy": "UPLIFT_DECISION",
                "action": action,
                "amount": float(row["amount"]),
                "predicted_recovery_probability": (
                    selected_value.recovery_probability
                ),
                "estimated_uplift": selected_value.estimated_uplift,
                "predicted_expected_net_value": selected_value.expected_net_value,
                "predicted_incremental_value": selected_value.incremental_value,
                **evaluate_ground_truth(row=row, action=action),
            }
        )

        if index % 1_000 == 0:
            print(f"Uplift decisions evaluated: {index:,}/{len(df):,}")

    return (
        aggregate_strategy("UPLIFT_DECISION", assignments),
        assignments,
    )


def evaluate_uplift_optimizer_strategy(
    df: pd.DataFrame,
    precomputed_decisions: dict[str, RecoveryDecision],
    context_by_payment: dict[str, dict],
) -> tuple[dict, list[dict], PortfolioOptimizationResult]:
    payments = []
    row_lookup = {}

    for _, row in df.iterrows():
        payment_id = str(row["payment_id"])
        payments.append(
            PortfolioPayment(
                payment_id=payment_id,
                context=context_by_payment[payment_id],
            )
        )
        row_lookup[payment_id] = row

    print("\nRunning uplift-aware OR-Tools portfolio optimization...")
    print(f"Portfolio size: {len(payments):,} payments")
    result = PortfolioOptimizer().optimize(
        payments=payments,
        constraints=PORTFOLIO_CONSTRAINTS,
        policy=POLICY,
        precomputed_decisions=precomputed_decisions,
    )
    print(f"Optimizer status: {result.status}")

    assignments = []
    for assignment in result.assignments:
        row = row_lookup[assignment.payment_id]
        decision = precomputed_decisions[assignment.payment_id]
        selected_value = selected_economic_value(decision, assignment.action)
        if selected_value is None:
            raise ValueError(
                f"Optimized value missing for payment {assignment.payment_id}"
            )

        assignments.append(
            {
                "payment_id": assignment.payment_id,
                "strategy": "UPLIFT_OPTIMIZED",
                "action": assignment.action,
                "amount": float(row["amount"]),
                "predicted_recovery_probability": (
                    assignment.recovery_probability
                ),
                "estimated_uplift": selected_value.estimated_uplift,
                "predicted_expected_net_value": assignment.expected_net_value,
                "predicted_incremental_value": assignment.incremental_value,
                **evaluate_ground_truth(row=row, action=assignment.action),
            }
        )

    return (
        aggregate_strategy("UPLIFT_OPTIMIZED", assignments),
        assignments,
        result,
    )


def normalize_baseline_assignments(assignments: list[dict]) -> list[dict]:
    return [
        {
            **assignment,
            "predicted_recovery_probability": None,
            "estimated_uplift": None,
            "predicted_expected_net_value": None,
            "predicted_incremental_value": None,
        }
        for assignment in assignments
    ]


def comparison_rows(results: list[dict]) -> list[dict]:
    baseline_net = next(
        result["expected_net_revenue"]
        for result in results
        if result["strategy"] == "BASELINE"
    )
    rows = []

    for result in results:
        difference = result["expected_net_revenue"] - baseline_net
        rows.append(
            {
                "strategy": result["strategy"],
                "payments": result["payments"],
                "revenue_at_risk": result["revenue_at_risk"],
                "expected_recovery_rate": result["expected_recovery_rate"],
                "expected_gross_revenue": result["expected_gross_revenue"],
                "intervention_spend": result["intervention_spend"],
                "incentive_spend": result["incentive_spend"],
                "expected_net_revenue": result["expected_net_revenue"],
                "additional_net_revenue_vs_baseline": difference,
                "net_uplift_percent_vs_baseline": (
                    difference / baseline_net * 100.0 if baseline_net else 0.0
                ),
                "retry_count": result["retry_count"],
                "customer_contact_count": result["customer_contact_count"],
                "do_nothing_count": result["do_nothing_count"],
            }
        )

    return rows


def print_comparison(results: list[dict]) -> None:
    print("\nRECOVERIQ UPLIFT STRATEGY COMPARISON")
    print("=" * 105)
    print(
        f"{'STRATEGY':20s}{'RECOVERY':>12s}{'GROSS REVENUE':>20s}"
        f"{'INTERVENTION':>16s}{'INCENTIVE':>16s}{'NET REVENUE':>20s}"
    )
    print("-" * 105)
    for result in results:
        print(
            f"{result['strategy']:20s}"
            f"{result['expected_recovery_rate']:>11.2%}"
            f"{format_currency(result['expected_gross_revenue']):>20s}"
            f"{format_currency(result['intervention_spend']):>16s}"
            f"{format_currency(result['incentive_spend']):>16s}"
            f"{format_currency(result['expected_net_revenue']):>20s}"
        )

    rows = comparison_rows(results)
    print("\nUPLIFT VS BASELINE")
    for row in rows[1:]:
        print(
            f"  {row['strategy']}: "
            f"{format_currency(row['additional_net_revenue_vs_baseline'])} "
            f"({row['net_uplift_percent_vs_baseline']:+.2f}%)"
        )

    print("\nACTION DISTRIBUTIONS")
    for result in results:
        print(f"\n{result['strategy']}")
        for action in sorted(CANONICAL_ACTIONS):
            print(f"  {action:20s}{result['action_counts'].get(action, 0):>8,}")


def optimizer_resource_usage(assignments: list[dict]) -> dict[str, float | int]:
    action_counts = Counter(item["action"] for item in assignments)
    return {
        "total_intervention_and_incentive_spend": sum(
            item["intervention_cost"] + item["incentive_cost"]
            for item in assignments
        ),
        "incentive_spend": sum(item["incentive_cost"] for item in assignments),
        "retry_actions": sum(
            action_counts[action] for action in RETRY_ACTIONS
        ),
        "customer_contacts": sum(
            action_counts[action] for action in CUSTOMER_CONTACT_ACTIONS
        ),
        "whatsapp_actions": action_counts["WHATSAPP"],
        "incentive_actions": action_counts["INCENTIVE"],
        "human_escalations": action_counts["HUMAN_ESCALATION"],
    }


def print_resource_usage(usage: dict[str, float | int]) -> None:
    print("\nUPLIFT_OPTIMIZED PORTFOLIO RESOURCE USAGE")
    for name, value in usage.items():
        display = format_currency(value) if "spend" in name else f"{value:,}"
        print(f"  {name}: {display}")


def save_results(results: list[dict], assignments: list[dict]) -> None:
    pd.DataFrame(comparison_rows(results)).to_csv(
        COMPARISON_OUTPUT_PATH,
        index=False,
    )
    pd.DataFrame(assignments).to_csv(
        ASSIGNMENTS_OUTPUT_PATH,
        index=False,
    )
    print("\nResults saved to:")
    print(COMPARISON_OUTPUT_PATH)
    print(ASSIGNMENTS_OUTPUT_PATH)


def run_sanity_checks(
    df: pd.DataFrame,
    results: list[dict],
    assignments_by_strategy: dict[str, list[dict]],
    precomputed_decisions: dict[str, RecoveryDecision],
    optimizer_result: PortfolioOptimizationResult,
    phase_17_hashes: dict[Path, str],
) -> None:
    if len(df) != EXPECTED_PAYMENTS:
        raise AssertionError(f"Expected exactly {EXPECTED_PAYMENTS:,} payments")

    for result in results:
        if result["payments"] != EXPECTED_PAYMENTS:
            raise AssertionError(f"{result['strategy']} does not cover all payments")
        numeric_metrics = [
            value
            for key, value in result.items()
            if key != "action_counts" and isinstance(value, (int, float))
        ]
        if not all(math.isfinite(value) for value in numeric_metrics):
            raise AssertionError(f"{result['strategy']} contains non-finite metrics")
        expected_net = (
            result["expected_gross_revenue"]
            - result["intervention_spend"]
            - result["incentive_spend"]
        )
        if not math.isclose(
            result["expected_net_revenue"],
            expected_net,
            rel_tol=0.0,
            abs_tol=1e-5,
        ):
            raise AssertionError(f"{result['strategy']} net revenue does not reconcile")

    expected_payment_ids = set(df["payment_id"].astype(str))
    for strategy, assignments in assignments_by_strategy.items():
        if len(assignments) != EXPECTED_PAYMENTS:
            raise AssertionError(f"{strategy} must assign exactly one action per payment")
        payment_ids = [item["payment_id"] for item in assignments]
        if len(set(payment_ids)) != EXPECTED_PAYMENTS:
            raise AssertionError(f"{strategy} contains duplicate payment assignments")
        if set(payment_ids) != expected_payment_ids:
            raise AssertionError(f"{strategy} payment coverage differs from test data")
        if not all(item["action"] in CANONICAL_ACTIONS for item in assignments):
            raise AssertionError(f"{strategy} contains a non-canonical action")

    if optimizer_result.status not in {"OPTIMAL", "FEASIBLE"}:
        raise AssertionError("Optimizer did not produce a usable solution")

    if not all(
        any(item.action == RecoveryAction.DO_NOTHING.value for item in decision.ranked_actions)
        for decision in precomputed_decisions.values()
    ):
        raise AssertionError("DO_NOTHING is not feasible for every payment")

    optimized_assignments = assignments_by_strategy["UPLIFT_OPTIMIZED"]
    usage = optimizer_resource_usage(optimized_assignments)
    constraints: PortfolioConstraints = PORTFOLIO_CONSTRAINTS
    constraint_checks = {
        "total spend": (
            usage["total_intervention_and_incentive_spend"],
            constraints.max_total_intervention_spend,
        ),
        "incentive spend": (
            usage["incentive_spend"], constraints.max_incentive_spend
        ),
        "retry actions": (usage["retry_actions"], constraints.max_retry_actions),
        "customer contacts": (
            usage["customer_contacts"], constraints.max_customer_contacts
        ),
        "WhatsApp actions": (
            usage["whatsapp_actions"], constraints.max_whatsapp_actions
        ),
        "incentive actions": (
            usage["incentive_actions"], constraints.max_incentive_actions
        ),
        "human escalations": (
            usage["human_escalations"], constraints.max_human_escalations
        ),
    }
    for name, (actual, limit) in constraint_checks.items():
        if limit is not None and actual > limit + 1e-6:
            raise AssertionError(f"Optimizer exceeded {name}: {actual} > {limit}")

    if not COMPARISON_OUTPUT_PATH.exists() or not ASSIGNMENTS_OUTPUT_PATH.exists():
        raise AssertionError("Phase 18F output files were not created")
    for path, original_hash in phase_17_hashes.items():
        if file_sha256(path) != original_hash:
            raise AssertionError(f"Frozen Phase 17 output changed: {path}")

    print("\nAll uplift strategy sanity checks passed.")


def main() -> None:
    phase_17_hashes = capture_phase_17_hashes()

    print("Loading frozen test set...")
    df = pd.read_csv(TEST_PATH)
    print(f"Loaded {len(df):,} payments.")
    if len(df) != EXPECTED_PAYMENTS:
        raise ValueError(
            f"Expected {EXPECTED_PAYMENTS:,} frozen test payments, found {len(df):,}"
        )

    print("\nEvaluating fixed baseline...")
    baseline_metrics, baseline_assignments = evaluate_baseline(df)
    print("Baseline complete.")

    print("\nPrecomputing uplift-aware decisions...")
    precomputed_decisions, context_by_payment = (
        build_precomputed_uplift_decisions(df)
    )

    print("\nEvaluating uplift-aware independent decisions...")
    uplift_metrics, uplift_assignments = evaluate_uplift_decision_strategy(
        df,
        precomputed_decisions,
    )
    print("Uplift-aware independent decision strategy complete.")

    (
        optimized_metrics,
        optimized_assignments,
        optimizer_result,
    ) = evaluate_uplift_optimizer_strategy(
        df,
        precomputed_decisions,
        context_by_payment,
    )
    print("Uplift-aware portfolio optimizer complete.")

    results = [baseline_metrics, uplift_metrics, optimized_metrics]
    baseline_output_assignments = normalize_baseline_assignments(
        baseline_assignments
    )
    all_assignments = (
        baseline_output_assignments + uplift_assignments + optimized_assignments
    )
    assignments_by_strategy = {
        "BASELINE": baseline_output_assignments,
        "UPLIFT_DECISION": uplift_assignments,
        "UPLIFT_OPTIMIZED": optimized_assignments,
    }

    print_comparison(results)
    usage = optimizer_resource_usage(optimized_assignments)
    print_resource_usage(usage)
    save_results(results, all_assignments)
    run_sanity_checks(
        df,
        results,
        assignments_by_strategy,
        precomputed_decisions,
        optimizer_result,
        phase_17_hashes,
    )


if __name__ == "__main__":
    main()
