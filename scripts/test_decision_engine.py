from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(
    str(ROOT)
)

sys.path.append(
    str(ROOT / "backend")
)


from app.decision.decision_engine import (
    DecisionEngine,
)


def main():

    context = {
        "amount": 2500.0,

        "payment_method": "UPI",

        "failure_code": "BANK_TIMEOUT",

        "failure_type":
            "TEMPORARY_BANK_FAILURE",

        "attempt_number": 1,

        "hour": 14,

        "day_of_week": 2,

        "customer_tenure_days": 500,

        "successful_payments": 12,

        "failed_payments": 3,

        "previous_recoveries": 2,

        "historical_recovery_rate": 0.67,

        "avg_transaction_value": 2200.0,

        "whatsapp_response_rate": 0.45,

        "email_response_rate": 0.30,

        "retry_success_rate": 0.75,

        "payment_link_conversion_rate": 0.40,

        "price_sensitivity": 0.50,
    }

    print(
        "\nLoading decision engine..."
    )

    engine = DecisionEngine()

    print(
        "Decision engine loaded successfully."
    )

    decision = (
        engine.evaluate(
            context
        )
    )

    print(
        "\n=============================="
    )

    print(
        "ECONOMIC DECISION ENGINE"
    )

    print(
        "==============================\n"
    )

    print(
        f"Payment amount: "
        f"₹{context['amount']:,.2f}"
    )

    print(
        f"Failure type: "
        f"{context['failure_type']}"
    )

    print(
        "\nRanked recovery actions:\n"
    )

    for item in decision.ranked_actions:

        total_cost = (
            item.intervention_cost
            + item.incentive_cost
        )

        print(
            f"{item.action:20s}"
            f" "
            f"P={item.recovery_probability:.4f}"
            f" "
            f"Gross=₹{item.expected_gross_value:,.2f}"
            f" "
            f"Cost=₹{total_cost:,.2f}"
            f" "
            f"Net=₹{item.expected_net_value:,.2f}"
            f" "
            f"Incremental=₹{item.incremental_value:,.2f}"
        )

    print(
        "\n------------------------------"
    )

    print(
        "Recommended action:",
        decision.recommended_action,
    )

    print(
        "Recovery probability:",
        f"{decision.recovery_probability:.2%}",
    )

    print(
        "Expected net value:",
        f"₹{decision.expected_net_value:,.2f}",
    )

    print(
        "Incremental value:",
        f"₹{decision.incremental_value:,.2f}",
    )

    print(
        "------------------------------"
    )

    # -----------------------------------------
    # Sanity checks
    # -----------------------------------------

    assert (
        len(decision.ranked_actions)
        == 9
    )

    do_nothing = next(
        item
        for item in decision.ranked_actions
        if item.action == "DO_NOTHING"
    )

    assert abs(
        do_nothing.incremental_value
    ) < 1e-9

    assert all(
        0
        <= item.recovery_probability
        <= 1
        for item
        in decision.ranked_actions
    )

    net_values = [
        item.expected_net_value
        for item
        in decision.ranked_actions
    ]

    assert (
        net_values
        == sorted(
            net_values,
            reverse=True,
        )
    )

    print(
        "\nAll decision-engine "
        "sanity checks passed."
    )


if __name__ == "__main__":
    main()