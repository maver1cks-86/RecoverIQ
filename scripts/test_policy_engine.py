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

from app.policies.engine import (
    PolicyConfig,
)


def main():

    context = {
        "amount": 2500.0,

        "payment_method": "UPI",

        "failure_code": "BANK_TIMEOUT",

        "failure_type":
            "TEMPORARY_BANK_FAILURE",

        # We deliberately use attempt 3
        # so retries should be blocked.
        "attempt_number": 3,

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

        # Required by policy layer,
        # not by ML model.
        "customer_contact_count": 1,
    }

    policy = PolicyConfig(
        max_retry_attempts=3,

        max_customer_contacts=3,

        incentives_enabled=False,

        human_escalation_enabled=True,

        max_incentive_amount=500.0,

        min_amount_for_human_escalation=1000.0,
    )

    engine = DecisionEngine()

    decision = engine.evaluate(
        context=context,
        policy=policy,
    )

    print(
        "\n=================================="
    )

    print(
        "RECOVERIQ POLICY ENGINE TEST"
    )

    print(
        "==================================\n"
    )

    print(
        f"Amount: "
        f"₹{context['amount']:,.2f}"
    )

    print(
        f"Failure: "
        f"{context['failure_type']}"
    )

    print(
        f"Attempt: "
        f"{context['attempt_number']}"
    )

    print(
        "\nPOLICY RESULTS\n"
    )

    for result in decision.policy_decisions:

        status = (
            "ALLOWED"
            if result.allowed
            else "BLOCKED"
        )

        print(
            f"{result.action:20s}"
            f" {status:8s}"
            f" | {result.reason}"
        )

    print(
        "\n----------------------------------"
    )

    print(
        "ELIGIBLE ACTION RANKING"
    )

    print(
        "----------------------------------\n"
    )

    for item in decision.ranked_actions:

        print(
            f"{item.action:20s}"
            f" "
            f"P={item.recovery_probability:.4f}"
            f" "
            f"Net=₹{item.expected_net_value:,.2f}"
            f" "
            f"Incremental="
            f"₹{item.incremental_value:,.2f}"
        )

    print(
        "\n----------------------------------"
    )

    print(
        "Recommended action:",
        decision.recommended_action,
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
        "----------------------------------"
    )

    # =========================================
    # SANITY CHECKS
    # =========================================

    policy_map = {
        result.action:
            result
        for result
        in decision.policy_decisions
    }

    # Retry actions should be blocked
    # because attempt_number == max retries.

    assert (
        policy_map[
            "RETRY_NOW"
        ].allowed
        is False
    )

    assert (
        policy_map[
            "RETRY_LATER"
        ].allowed
        is False
    )

    # Incentive explicitly disabled.

    assert (
        policy_map[
            "INCENTIVE"
        ].allowed
        is False
    )

    # DO_NOTHING must always survive.

    assert (
        policy_map[
            "DO_NOTHING"
        ].allowed
        is True
    )

    eligible_actions = {
        item.action
        for item
        in decision.ranked_actions
    }

    assert (
        "RETRY_NOW"
        not in eligible_actions
    )

    assert (
        "RETRY_LATER"
        not in eligible_actions
    )

    assert (
        "INCENTIVE"
        not in eligible_actions
    )

    assert (
        "DO_NOTHING"
        in eligible_actions
    )

    print(
        "\nAll policy-engine "
        "sanity checks passed."
    )


if __name__ == "__main__":
    main()