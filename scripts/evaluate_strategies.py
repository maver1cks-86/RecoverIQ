from pathlib import Path
import sys
from collections import Counter

import pandas as pd


# ============================================================
# PATH SETUP
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(BACKEND_ROOT))


# ============================================================
# PROJECT IMPORTS
# ============================================================

from app.decision.baseline import (
    choose_baseline_action,
)

from app.decision.decision_engine import (
    DecisionEngine,
)

from app.optimizer.portfolio_optimizer import (
    PortfolioConstraints,
    PortfolioOptimizer,
    PortfolioPayment,
)

from app.policies.engine import (
    PolicyConfig,
)

from scripts.generate_dateset import (
    ACTION_COSTS,
    calculate_incentive,
    calculate_recovery_probability,
)


# ============================================================
# PATHS
# ============================================================

TEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "test.csv"
)

COMPARISON_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "strategy_comparison.csv"
)

ASSIGNMENTS_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "strategy_assignments.csv"
)


# ============================================================
# PORTFOLIO CONFIGURATION
# ============================================================

#
# These are intentionally finite.
#
# We want Phase 17 to demonstrate that RecoverIQ
# decides WHERE scarce recovery resources should go.
#

PORTFOLIO_CONSTRAINTS = PortfolioConstraints(
    max_total_intervention_spend=20_000.0,
    max_incentive_spend=10_000.0,
    max_retry_actions=3_500,
    max_customer_contacts=3_000,
    max_whatsapp_actions=1_500,
    max_incentive_actions=500,
    max_human_escalations=300,
    solver_time_limit_ms=120_000,
)


POLICY = PolicyConfig(
    max_retry_attempts=3,
    max_customer_contacts=3,
    incentives_enabled=True,
    human_escalation_enabled=True,
    max_incentive_amount=500.0,
    min_amount_for_human_escalation=1000.0,
)


# ============================================================
# CUSTOMER / PAYMENT BUILDERS
# ============================================================


def build_customer(row: pd.Series) -> dict:
    """
    Reconstruct the customer state expected by the
    frozen synthetic ground-truth simulator.
    """

    return {
        "customer_tenure_days":
            int(row["customer_tenure_days"]),

        "successful_payments":
            int(row["successful_payments"]),

        "failed_payments":
            int(row["failed_payments"]),

        "previous_recoveries":
            int(row["previous_recoveries"]),

        "historical_recovery_rate":
            float(row["historical_recovery_rate"]),

        "avg_transaction_value":
            float(row["avg_transaction_value"]),

        "whatsapp_response_rate":
            float(row["whatsapp_response_rate"]),

        "email_response_rate":
            float(row["email_response_rate"]),

        "retry_success_rate":
            float(row["retry_success_rate"]),

        "payment_link_conversion_rate":
            float(
                row[
                    "payment_link_conversion_rate"
                ]
            ),

        "price_sensitivity":
            float(row["price_sensitivity"]),
    }


def build_payment(row: pd.Series) -> dict:
    """
    Reconstruct the payment state expected by
    calculate_recovery_probability().
    """

    return {
        "amount":
            float(row["amount"]),

        "payment_method":
            str(row["payment_method"]),

        "failure_type":
            str(row["failure_type"]),

        "failure_code":
            str(row["failure_code"]),

        "attempt_number":
            int(row["attempt_number"]),

        "hour":
            int(row["hour"]),

        "day_of_week":
            int(row["day_of_week"]),
    }


def build_decision_context(
    row: pd.Series,
) -> dict:
    """
    Context expected by DecisionEngine / ML model.
    """

    return {
        "amount":
            float(row["amount"]),

        "payment_method":
            str(row["payment_method"]),

        "failure_code":
            str(row["failure_code"]),

        "failure_type":
            str(row["failure_type"]),

        "attempt_number":
            int(row["attempt_number"]),

        "hour":
            int(row["hour"]),

        "day_of_week":
            int(row["day_of_week"]),

        "customer_tenure_days":
            int(row["customer_tenure_days"]),

        "successful_payments":
            int(row["successful_payments"]),

        "failed_payments":
            int(row["failed_payments"]),

        "previous_recoveries":
            int(row["previous_recoveries"]),

        "historical_recovery_rate":
            float(
                row[
                    "historical_recovery_rate"
                ]
            ),

        "avg_transaction_value":
            float(
                row[
                    "avg_transaction_value"
                ]
            ),

        "whatsapp_response_rate":
            float(
                row[
                    "whatsapp_response_rate"
                ]
            ),

        "email_response_rate":
            float(
                row[
                    "email_response_rate"
                ]
            ),

        "retry_success_rate":
            float(
                row[
                    "retry_success_rate"
                ]
            ),

        "payment_link_conversion_rate":
            float(
                row[
                    "payment_link_conversion_rate"
                ]
            ),

        "price_sensitivity":
            float(
                row[
                    "price_sensitivity"
                ]
            ),

        # Not present in the synthetic dataset.
        # Phase 14 policy supports it, so we explicitly
        # initialize it to zero for evaluation.
        "customer_contact_count": 0,
    }


# ============================================================
# GROUND-TRUTH EVALUATION
# ============================================================


def evaluate_ground_truth(
    row: pd.Series,
    action: str,
) -> dict:
    """
    Evaluate a chosen action using the frozen simulator.

    IMPORTANT:
    We do NOT use row["recovered"] because that outcome
    belongs to the action originally assigned during
    observational dataset generation.

    Instead we compute the counterfactual expected outcome
    for the action selected by the strategy.
    """

    customer = build_customer(row)
    payment = build_payment(row)

    probability = (
        calculate_recovery_probability(
            customer=customer,
            payment=payment,
            action=action,
            add_noise=False,
        )
    )

    amount = float(row["amount"])

    intervention_cost = float(
        ACTION_COSTS[action]
    )

    incentive_cost = float(
        calculate_incentive(
            action,
            amount,
        )
    )

    expected_gross_revenue = (
        probability * amount
    )

    expected_net_revenue = (
        expected_gross_revenue
        - intervention_cost
        - incentive_cost
    )

    return {
        "true_recovery_probability":
            probability,

        "expected_gross_revenue":
            expected_gross_revenue,

        "expected_net_revenue":
            expected_net_revenue,

        "intervention_cost":
            intervention_cost,

        "incentive_cost":
            incentive_cost,
    }


# ============================================================
# METRIC AGGREGATION
# ============================================================


def aggregate_strategy(
    strategy_name: str,
    assignments: list[dict],
) -> dict:

    total_payments = len(assignments)

    total_amount = sum(
        item["amount"]
        for item in assignments
    )

    expected_recoveries = sum(
        item[
            "true_recovery_probability"
        ]
        for item in assignments
    )

    expected_gross_revenue = sum(
        item[
            "expected_gross_revenue"
        ]
        for item in assignments
    )

    expected_net_revenue = sum(
        item[
            "expected_net_revenue"
        ]
        for item in assignments
    )

    intervention_spend = sum(
        item[
            "intervention_cost"
        ]
        for item in assignments
    )

    incentive_spend = sum(
        item[
            "incentive_cost"
        ]
        for item in assignments
    )

    retries = sum(
        1
        for item in assignments
        if item["action"]
        in {
            "RETRY_NOW",
            "RETRY_LATER",
        }
    )

    contacts = sum(
        1
        for item in assignments
        if item["action"]
        in {
            "WHATSAPP",
            "EMAIL",
            "PAYMENT_LINK",
            "INCENTIVE",
            "HUMAN_ESCALATION",
        }
    )

    do_nothing = sum(
        1
        for item in assignments
        if item["action"]
        == "DO_NOTHING"
    )

    expected_recovery_rate = (
        expected_recoveries
        / total_payments
    )

    action_counts = Counter(
        item["action"]
        for item in assignments
    )

    return {
        "strategy":
            strategy_name,

        "payments":
            total_payments,

        "revenue_at_risk":
            total_amount,

        "expected_recovery_rate":
            expected_recovery_rate,

        "expected_gross_revenue":
            expected_gross_revenue,

        "intervention_spend":
            intervention_spend,

        "incentive_spend":
            incentive_spend,

        "expected_net_revenue":
            expected_net_revenue,

        "retry_count":
            retries,

        "customer_contact_count":
            contacts,

        "do_nothing_count":
            do_nothing,

        "action_counts":
            dict(action_counts),
    }

# ============================================================
# BATCH ML PRECOMPUTATION
# ============================================================


def build_precomputed_decisions(
    df: pd.DataFrame,
) -> dict:
    """
    Batch-predict every payment/action combination once.

    Instead of:

        10,000 payments
        x 9 actions
        x repeated predict_proba() calls

    we construct one 90,000-row batch and call
    predict_proba() once.

    The resulting RecoveryDecision objects are then
    shared by:

        Strategy B — independent ML decisioning
        Strategy C — portfolio optimization

    This guarantees both strategies use exactly the
    same ML predictions and avoids repeated inference.
    """

    print(
        "\nPreparing contexts for batch ML inference..."
    )

    contexts = []

    payment_ids = []

    for _, row in df.iterrows():

        payment_ids.append(
            str(
                row["payment_id"]
            )
        )

        contexts.append(
            build_decision_context(
                row
            )
        )

    print(
        f"Prepared {len(contexts):,} payment contexts."
    )

    engine = DecisionEngine()

    print(
        f"Batch predicting "
        f"{len(contexts):,} payments "
        f"across all candidate actions..."
    )

    # --------------------------------------------------------
    # This is the important part:
    #
    # RecoveryPredictor.predict_probabilities_batch()
    # will create approximately:
    #
    # 10,000 payments x 9 actions = 90,000 rows
    #
    # and send them through predict_proba() in one call.
    # --------------------------------------------------------

    batch_predictions = (
        engine
        .action_evaluator
        .evaluate_batch(
            contexts
        )
    )

    print(
        "Batch ML prediction complete."
    )

    print(
        "Applying economics and policy rules..."
    )

    decisions = {}

    total = len(
        contexts
    )

    for index, (
        payment_id,
        context,
        predictions,
    ) in enumerate(
        zip(
            payment_ids,
            contexts,
            batch_predictions,
        ),
        start=1,
    ):

        decision = (
            engine
            .evaluate_from_predictions(
                context=context,
                predictions=predictions,
                policy=POLICY,
            )
        )

        decisions[
            payment_id
        ] = decision

        if index % 1000 == 0:

            print(
                f"Decisions prepared: "
                f"{index:,}/{total:,}"
            )

    print(
        f"Precomputed "
        f"{len(decisions):,} decisions."
    )

    return decisions
# ============================================================
# STRATEGY A — FIXED BASELINE
# ============================================================


def evaluate_baseline(
    df: pd.DataFrame,
) -> tuple[dict, list[dict]]:

    assignments = []

    for _, row in df.iterrows():

        decision = choose_baseline_action(
            failure_type=str(
                row["failure_type"]
            ),
            attempt_number=int(
                row["attempt_number"]
            ),
        )

        evaluation = evaluate_ground_truth(
            row=row,
            action=decision.action,
        )

        assignments.append(
            {
                "payment_id":
                    str(row["payment_id"]),

                "strategy":
                    "BASELINE",

                "action":
                    decision.action,

                "amount":
                    float(row["amount"]),

                **evaluation,
            }
        )

    metrics = aggregate_strategy(
        strategy_name="BASELINE",
        assignments=assignments,
    )

    return metrics, assignments


# ============================================================
# STRATEGY B — INDEPENDENT ML DECISION
# ============================================================


def evaluate_ml_strategy(
    df: pd.DataFrame,
    precomputed_decisions: dict,
) -> tuple[dict, list[dict]]:
    """
    Evaluate the independent ML strategy using
    decisions that were already batch-computed.

    No ML inference happens inside this function.
    """

    assignments = []

    total = len(
        df
    )

    for index, (_, row) in enumerate(
        df.iterrows(),
        start=1,
    ):

        payment_id = str(
            row["payment_id"]
        )

        if (
            payment_id
            not in precomputed_decisions
        ):
            raise ValueError(
                f"Missing precomputed decision "
                f"for payment {payment_id}."
            )

        decision = (
            precomputed_decisions[
                payment_id
            ]
        )

        action = (
            decision.recommended_action
        )

        evaluation = evaluate_ground_truth(
            row=row,
            action=action,
        )

        assignments.append(
            {
                "payment_id":
                    payment_id,

                "strategy":
                    "ML_DECISION",

                "action":
                    action,

                "amount":
                    float(
                        row["amount"]
                    ),

                **evaluation,
            }
        )

        if index % 1000 == 0:

            print(
                f"ML decisions evaluated: "
                f"{index:,}/{total:,}"
            )

    metrics = aggregate_strategy(
        strategy_name="ML_DECISION",
        assignments=assignments,
    )

    return (
        metrics,
        assignments,
    )

# ============================================================
# STRATEGY C — PORTFOLIO OPTIMIZER
# ============================================================


def evaluate_optimizer_strategy(
    df: pd.DataFrame,
    precomputed_decisions: dict,
) -> tuple[dict, list[dict]]:
    """
    Run portfolio optimization using the same
    precomputed ML decisions used by Strategy B.

    The optimizer therefore performs no repeated
    ML inference.
    """

    optimizer = PortfolioOptimizer()

    portfolio_payments = []

    row_lookup = {}

    for _, row in df.iterrows():

        payment_id = str(
            row["payment_id"]
        )

        context = (
            build_decision_context(
                row
            )
        )

        portfolio_payments.append(
            PortfolioPayment(
                payment_id=payment_id,
                context=context,
            )
        )

        row_lookup[
            payment_id
        ] = row

    print(
        "\nRunning OR-Tools portfolio optimization..."
    )

    print(
        f"Portfolio size: "
        f"{len(portfolio_payments):,} payments"
    )

    result = optimizer.optimize(
        payments=portfolio_payments,
        constraints=PORTFOLIO_CONSTRAINTS,
        policy=POLICY,
        precomputed_decisions=(
            precomputed_decisions
        ),
    )

    print(
        "Optimizer status:",
        result.status,
    )

    assignments = []

    for assignment in result.assignments:

        row = row_lookup[
            assignment.payment_id
        ]

        evaluation = evaluate_ground_truth(
            row=row,
            action=assignment.action,
        )

        assignments.append(
            {
                "payment_id":
                    assignment.payment_id,

                "strategy":
                    "OPTIMIZED",

                "action":
                    assignment.action,

                "amount":
                    float(
                        row["amount"]
                    ),

                **evaluation,
            }
        )

    metrics = aggregate_strategy(
        strategy_name="OPTIMIZED",
        assignments=assignments,
    )

    return (
        metrics,
        assignments,
    )
# ============================================================
# DISPLAY
# ============================================================


def format_currency(
    value: float,
) -> str:
    return f"₹{value:,.2f}"


def print_comparison(
    results: list[dict],
) -> None:

    result_map = {
        result["strategy"]:
            result
        for result in results
    }

    baseline = result_map[
        "BASELINE"
    ]

    ml = result_map[
        "ML_DECISION"
    ]

    optimized = result_map[
        "OPTIMIZED"
    ]

    print(
        "\n"
        "============================================================"
    )

    print(
        "RECOVERIQ STRATEGY COMPARISON"
    )

    print(
        "============================================================\n"
    )

    header = (
        f"{'METRIC':30s}"
        f"{'BASELINE':>18s}"
        f"{'ML DECISION':>18s}"
        f"{'OPTIMIZED':>18s}"
    )

    print(header)

    print("-" * len(header))

    print(
        f"{'Payments':30s}"
        f"{baseline['payments']:>18,}"
        f"{ml['payments']:>18,}"
        f"{optimized['payments']:>18,}"
    )

    print(
        f"{'Revenue at risk':30s}"
        f"{format_currency(baseline['revenue_at_risk']):>18s}"
        f"{format_currency(ml['revenue_at_risk']):>18s}"
        f"{format_currency(optimized['revenue_at_risk']):>18s}"
    )

    print(
        f"{'Expected recovery rate':30s}"
        f"{baseline['expected_recovery_rate']:>17.2%}"
        f"{ml['expected_recovery_rate']:>17.2%}"
        f"{optimized['expected_recovery_rate']:>17.2%}"
    )

    print(
        f"{'Expected gross revenue':30s}"
        f"{format_currency(baseline['expected_gross_revenue']):>18s}"
        f"{format_currency(ml['expected_gross_revenue']):>18s}"
        f"{format_currency(optimized['expected_gross_revenue']):>18s}"
    )

    print(
        f"{'Intervention spend':30s}"
        f"{format_currency(baseline['intervention_spend']):>18s}"
        f"{format_currency(ml['intervention_spend']):>18s}"
        f"{format_currency(optimized['intervention_spend']):>18s}"
    )

    print(
        f"{'Incentive spend':30s}"
        f"{format_currency(baseline['incentive_spend']):>18s}"
        f"{format_currency(ml['incentive_spend']):>18s}"
        f"{format_currency(optimized['incentive_spend']):>18s}"
    )

    print(
        f"{'Expected net revenue':30s}"
        f"{format_currency(baseline['expected_net_revenue']):>18s}"
        f"{format_currency(ml['expected_net_revenue']):>18s}"
        f"{format_currency(optimized['expected_net_revenue']):>18s}"
    )

    print(
        f"{'Retries':30s}"
        f"{baseline['retry_count']:>18,}"
        f"{ml['retry_count']:>18,}"
        f"{optimized['retry_count']:>18,}"
    )

    print(
        f"{'Customer contacts':30s}"
        f"{baseline['customer_contact_count']:>18,}"
        f"{ml['customer_contact_count']:>18,}"
        f"{optimized['customer_contact_count']:>18,}"
    )

    print(
        f"{'Do nothing':30s}"
        f"{baseline['do_nothing_count']:>18,}"
        f"{ml['do_nothing_count']:>18,}"
        f"{optimized['do_nothing_count']:>18,}"
    )

    print(
        "\n"
        "------------------------------------------------------------"
    )

    print(
        "UPLIFT VS BASELINE"
    )

    print(
        "------------------------------------------------------------"
    )

    ml_difference = (
        ml["expected_net_revenue"]
        - baseline["expected_net_revenue"]
    )

    optimized_difference = (
        optimized[
            "expected_net_revenue"
        ]
        - baseline[
            "expected_net_revenue"
        ]
    )

    ml_percent = (
        ml_difference
        / baseline[
            "expected_net_revenue"
        ]
        * 100
    )

    optimized_percent = (
        optimized_difference
        / baseline[
            "expected_net_revenue"
        ]
        * 100
    )

    print(
        "ML additional expected net revenue:",
        format_currency(
            ml_difference
        ),
    )

    print(
        "ML net uplift vs baseline:",
        f"{ml_percent:.2f}%",
    )

    print()

    print(
        "Optimized additional expected net revenue:",
        format_currency(
            optimized_difference
        ),
    )

    print(
        "Optimized net uplift vs baseline:",
        f"{optimized_percent:.2f}%",
    )

    print(
        "\n"
        "------------------------------------------------------------"
    )

    print(
        "ACTION DISTRIBUTIONS"
    )

    print(
        "------------------------------------------------------------"
    )

    for result in results:

        print(
            f"\n{result['strategy']}"
        )

        for (
            action,
            count,
        ) in sorted(
            result[
                "action_counts"
            ].items()
        ):

            print(
                f"  {action:20s}"
                f"{count:>8,}"
            )


# ============================================================
# SAVE RESULTS
# ============================================================


def save_results(
    results: list[dict],
    all_assignments: list[dict],
) -> None:

    COMPARISON_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison_rows = []

    baseline_net = next(
        result[
            "expected_net_revenue"
        ]
        for result in results
        if result["strategy"]
        == "BASELINE"
    )

    for result in results:

        difference = (
            result[
                "expected_net_revenue"
            ]
            - baseline_net
        )

        uplift_percent = (
            (
                difference
                / baseline_net
            )
            * 100
            if baseline_net != 0
            else 0.0
        )

        comparison_rows.append(
            {
                "strategy":
                    result["strategy"],

                "payments":
                    result["payments"],

                "revenue_at_risk":
                    result[
                        "revenue_at_risk"
                    ],

                "expected_recovery_rate":
                    result[
                        "expected_recovery_rate"
                    ],

                "expected_gross_revenue":
                    result[
                        "expected_gross_revenue"
                    ],

                "intervention_spend":
                    result[
                        "intervention_spend"
                    ],

                "incentive_spend":
                    result[
                        "incentive_spend"
                    ],

                "expected_net_revenue":
                    result[
                        "expected_net_revenue"
                    ],

                "additional_net_revenue_vs_baseline":
                    difference,

                "net_uplift_percent_vs_baseline":
                    uplift_percent,

                "retry_count":
                    result[
                        "retry_count"
                    ],

                "customer_contact_count":
                    result[
                        "customer_contact_count"
                    ],

                "do_nothing_count":
                    result[
                        "do_nothing_count"
                    ],
            }
        )

    comparison_df = pd.DataFrame(
        comparison_rows
    )

    comparison_df.to_csv(
        COMPARISON_OUTPUT_PATH,
        index=False,
    )

    assignments_df = pd.DataFrame(
        all_assignments
    )

    assignments_df.to_csv(
        ASSIGNMENTS_OUTPUT_PATH,
        index=False,
    )

    print(
        "\nResults saved to:"
    )

    print(
        COMPARISON_OUTPUT_PATH
    )

    print(
        ASSIGNMENTS_OUTPUT_PATH
    )


# ============================================================
# SANITY CHECKS
# ============================================================


def run_sanity_checks(
    results: list[dict],
) -> None:

    for result in results:

        assert (
            result["payments"]
            > 0
        )

        assert (
            0
            <= result[
                "expected_recovery_rate"
            ]
            <= 1
        )

        assert (
            result[
                "expected_net_revenue"
            ]
            <= result[
                "expected_gross_revenue"
            ]
            + 1e-6
        )

        assert (
            result[
                "intervention_spend"
            ]
            >= 0
        )

        assert (
            result[
                "incentive_spend"
            ]
            >= 0
        )

    optimized = next(
        result
        for result in results
        if result["strategy"]
        == "OPTIMIZED"
    )

    assert (
        optimized[
            "retry_count"
        ]
        <= PORTFOLIO_CONSTRAINTS
        .max_retry_actions
    )

    assert (
        optimized[
            "customer_contact_count"
        ]
        <= PORTFOLIO_CONSTRAINTS
        .max_customer_contacts
    )

    assert (
        optimized[
            "intervention_spend"
        ]
        <= (
            PORTFOLIO_CONSTRAINTS
            .max_total_intervention_spend
            + 1e-6
        )
    )

    assert (
        optimized[
            "incentive_spend"
        ]
        <= (
            PORTFOLIO_CONSTRAINTS
            .max_incentive_spend
            + 1e-6
        )
    )

    print(
        "\nAll strategy-comparison "
        "sanity checks passed."
    )


# ============================================================
# MAIN
# ============================================================


def main():

    print(
        "Loading frozen test set..."
    )

    df = pd.read_csv(
        TEST_PATH
    )

    print(
        f"Loaded {len(df):,} payments."
    )

    # --------------------------------------------------------
    # STRATEGY A
    # Fixed rule baseline.
    # No ML required.
    # --------------------------------------------------------

    print(
        "\nEvaluating fixed baseline..."
    )

    (
        baseline_metrics,
        baseline_assignments,
    ) = evaluate_baseline(
        df
    )

    print(
        "Baseline complete."
    )

    # --------------------------------------------------------
    # SHARED ML PRECOMPUTATION
    #
    # All payment/action probabilities are predicted once.
    # Both Strategy B and Strategy C reuse them.
    # --------------------------------------------------------

    print(
        "\nPrecomputing ML decisions in batch..."
    )

    precomputed_decisions = (
        build_precomputed_decisions(
            df
        )
    )

    print(
        "Batch decision preparation complete."
    )

    # --------------------------------------------------------
    # STRATEGY B
    # Independent ML + economic decision.
    # --------------------------------------------------------

    print(
        "\nEvaluating independent ML decisions..."
    )

    (
        ml_metrics,
        ml_assignments,
    ) = evaluate_ml_strategy(
        df,
        precomputed_decisions,
    )

    print(
        "ML decision strategy complete."
    )

    # --------------------------------------------------------
    # STRATEGY C
    # Global constrained portfolio optimization.
    # Uses exactly the same ML scores as Strategy B.
    # --------------------------------------------------------

    (
        optimized_metrics,
        optimized_assignments,
    ) = evaluate_optimizer_strategy(
        df,
        precomputed_decisions,
    )

    print(
        "Portfolio optimizer complete."
    )

    # --------------------------------------------------------
    # COMPARISON
    # --------------------------------------------------------

    results = [
        baseline_metrics,
        ml_metrics,
        optimized_metrics,
    ]

    all_assignments = (
        baseline_assignments
        + ml_assignments
        + optimized_assignments
    )

    print_comparison(
        results
    )

    save_results(
        results,
        all_assignments,
    )

    run_sanity_checks(
        results
    )


if __name__ == "__main__":
    main()