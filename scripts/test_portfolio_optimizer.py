from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(
    str(ROOT)
)

sys.path.append(
    str(ROOT / "backend")
)


from app.optimizer.portfolio_optimizer import (
    PortfolioConstraints,
    PortfolioOptimizer,
    PortfolioPayment,
)

from app.policies.engine import (
    PolicyConfig,
)


def build_context(
    amount: float,
    customer_tenure_days: int,
    historical_recovery_rate: float,
) -> dict:

    return {
        "amount": amount,

        "payment_method": "UPI",

        "failure_code": "BANK_TIMEOUT",

        "failure_type":
            "TEMPORARY_BANK_FAILURE",

        "attempt_number": 1,

        "hour": 14,

        "day_of_week": 2,

        "customer_tenure_days":
            customer_tenure_days,

        "successful_payments": 12,

        "failed_payments": 3,

        "previous_recoveries": 2,

        "historical_recovery_rate":
            historical_recovery_rate,

        "avg_transaction_value":
            amount * 0.8,

        "whatsapp_response_rate": 0.45,

        "email_response_rate": 0.30,

        "retry_success_rate": 0.75,

        "payment_link_conversion_rate": 0.40,

        "price_sensitivity": 0.50,

        "customer_contact_count": 0,
    }


def main():

    payments = [

        PortfolioPayment(
            payment_id="PAY_001",
            context=build_context(
                amount=1000.0,
                customer_tenure_days=100,
                historical_recovery_rate=0.30,
            ),
        ),

        PortfolioPayment(
            payment_id="PAY_002",
            context=build_context(
                amount=2000.0,
                customer_tenure_days=200,
                historical_recovery_rate=0.40,
            ),
        ),

        PortfolioPayment(
            payment_id="PAY_003",
            context=build_context(
                amount=3000.0,
                customer_tenure_days=300,
                historical_recovery_rate=0.50,
            ),
        ),

        PortfolioPayment(
            payment_id="PAY_004",
            context=build_context(
                amount=5000.0,
                customer_tenure_days=500,
                historical_recovery_rate=0.60,
            ),
        ),

        PortfolioPayment(
            payment_id="PAY_005",
            context=build_context(
                amount=7500.0,
                customer_tenure_days=700,
                historical_recovery_rate=0.70,
            ),
        ),

        PortfolioPayment(
            payment_id="PAY_006",
            context=build_context(
                amount=10000.0,
                customer_tenure_days=900,
                historical_recovery_rate=0.80,
            ),
        ),
    ]

    # --------------------------------------------------------
    # Merchant-level policy
    # --------------------------------------------------------

    policy = PolicyConfig(
        max_retry_attempts=3,

        max_customer_contacts=3,

        incentives_enabled=True,

        human_escalation_enabled=True,

        max_incentive_amount=500.0,

        min_amount_for_human_escalation=1000.0,
    )

    # --------------------------------------------------------
    # Portfolio-level scarcity.
    #
    # Only TWO retry actions may be allocated
    # across the entire portfolio.
    # --------------------------------------------------------

    constraints = PortfolioConstraints(

        max_total_intervention_spend=1000.0,

        max_incentive_spend=500.0,

        max_retry_actions=2,

        max_customer_contacts=3,

        max_whatsapp_actions=1,

        max_incentive_actions=1,

        max_human_escalations=1,

        solver_time_limit_ms=5000,
    )

    optimizer = (
        PortfolioOptimizer()
    )

    print(
        "\nRunning portfolio optimization..."
    )

    result = (
        optimizer.optimize(
            payments=payments,
            constraints=constraints,
            policy=policy,
        )
    )

    print(
        "\n======================================"
    )

    print(
        "RECOVERIQ PORTFOLIO OPTIMIZER"
    )

    print(
        "======================================\n"
    )

    print(
        "Solver status:",
        result.status,
    )

    print(
        "\nOPTIMIZED ASSIGNMENTS\n"
    )

    for assignment in result.assignments:

        print(
            f"{assignment.payment_id:10s}"
            f" "
            f"{assignment.action:20s}"
            f" "
            f"P={assignment.recovery_probability:.4f}"
            f" "
            f"Net=₹{assignment.expected_net_value:,.2f}"
            f" "
            f"Incremental="
            f"₹{assignment.incremental_value:,.2f}"
        )

    print(
        "\n--------------------------------------"
    )

    print(
        "PORTFOLIO RESULTS"
    )

    print(
        "--------------------------------------"
    )

    print(
        "Total expected net value:",
        f"₹{result.total_expected_net_value:,.2f}",
    )

    print(
        "Total incremental value:",
        f"₹{result.total_incremental_value:,.2f}",
    )

    print(
        "Total intervention spend:",
        f"₹{result.total_intervention_spend:,.2f}",
    )

    print(
        "Total incentive spend:",
        f"₹{result.total_incentive_spend:,.2f}",
    )

    print(
        "Retry actions used:",
        result.retry_count,
    )

    print(
        "Customer contacts used:",
        result.customer_contact_count,
    )

    print(
        "\nAction distribution:"
    )

    for (
        action,
        count,
    ) in sorted(
        result.action_counts.items()
    ):

        print(
            f"{action:20s}"
            f" {count}"
        )

    # ========================================================
    # SANITY CHECKS
    # ========================================================

    assert (
        result.status
        in {
            "OPTIMAL",
            "FEASIBLE",
        }
    )

    # Exactly one assignment for every payment.

    assert (
        len(result.assignments)
        == len(payments)
    )

    assigned_payment_ids = {
        assignment.payment_id
        for assignment
        in result.assignments
    }

    expected_payment_ids = {
        payment.payment_id
        for payment
        in payments
    }

    assert (
        assigned_payment_ids
        == expected_payment_ids
    )

    # --------------------------------------------------------
    # Retry capacity must be respected.
    # --------------------------------------------------------

    assert (
        result.retry_count
        <= constraints.max_retry_actions
    )

    # --------------------------------------------------------
    # Contact capacity must be respected.
    # --------------------------------------------------------

    assert (
        result.customer_contact_count
        <= constraints.max_customer_contacts
    )

    # --------------------------------------------------------
    # Intervention budget.
    # --------------------------------------------------------

    assert (
        result.total_intervention_spend
        <= (
            constraints
            .max_total_intervention_spend
            + 1e-6
        )
    )

    # --------------------------------------------------------
    # Incentive budget.
    # --------------------------------------------------------

    assert (
        result.total_incentive_spend
        <= (
            constraints
            .max_incentive_spend
            + 1e-6
        )
    )

    # --------------------------------------------------------
    # Specific capacities.
    # --------------------------------------------------------

    assert (
        result.action_counts.get(
            "WHATSAPP",
            0,
        )
        <= constraints.max_whatsapp_actions
    )

    assert (
        result.action_counts.get(
            "INCENTIVE",
            0,
        )
        <= constraints.max_incentive_actions
    )

    assert (
        result.action_counts.get(
            "HUMAN_ESCALATION",
            0,
        )
        <= constraints.max_human_escalations
    )

    # Since DO_NOTHING has incremental value = 0,
    # optimizer should never deliberately choose
    # a negative-value intervention when DO_NOTHING
    # is feasible.

    for assignment in result.assignments:

        assert (
            assignment.incremental_value
            >= -1e-6
        )

    print(
        "\nAll portfolio-optimizer "
        "sanity checks passed."
    )


if __name__ == "__main__":
    main()