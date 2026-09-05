import math

import math
import sys
from pathlib import Path


# -------------------------------------------------
# Make backend/app importable when running this
# script from the RecoverIQ project root.
# -------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
from app.decision.decision_engine import DecisionEngine
from app.policies.engine import PolicyConfig


def main():
    context = {
        "amount": 2500.0,
        "attempt_number": 2,
        "hour": 14,
        "day_of_week": 2,

        "customer_tenure_days": 400,
        "successful_payments": 10,
        "failed_payments": 3,
        "previous_recoveries": 2,
        "historical_recovery_rate": 0.67,
        "avg_transaction_value": 2200.0,

        "whatsapp_response_rate": 0.7,
        "email_response_rate": 0.4,
        "retry_success_rate": 0.5,
        "payment_link_conversion_rate": 0.6,
        "price_sensitivity": 0.5,

        "payment_method": "UPI",
        "failure_code": "CUSTOMER_ACTION_REQUIRED",
        "failure_type": "CUSTOMER_ACTION_REQUIRED",

        "customer_contact_count": 0,
    }

    engine = DecisionEngine()

    decision = engine.evaluate(
        context=context,
        policy=PolicyConfig(),
    )

    print("\nUPLIFT-AWARE DECISION")
    print("=" * 80)

    print(
        f"Recommended action: {decision.recommended_action}"
    )

    print("\nRANKED ACTIONS")
    print("-" * 80)

    for item in decision.ranked_actions:
        print(
            f"{item.action:20} "
            f"P={item.recovery_probability:.4f} "
            f"uplift={item.estimated_uplift:+.4f} "
            f"net={item.expected_net_value:10.2f} "
            f"incremental={item.incremental_value:+10.2f}"
        )

    print("\nRunning sanity checks...")

    assert len(decision.ranked_actions) > 0

    # -------------------------------------------------
    # DO_NOTHING checks
    # -------------------------------------------------

    do_nothing = next(
        item
        for item in decision.ranked_actions
        if item.action == "DO_NOTHING"
    )

    assert do_nothing.estimated_uplift == 0.0
    assert do_nothing.incremental_value == 0.0

    amount = context["amount"]

    # -------------------------------------------------
    # Economic formula checks
    # -------------------------------------------------

    for item in decision.ranked_actions:

        assert 0.0 <= item.recovery_probability <= 1.0

        assert math.isfinite(
            item.estimated_uplift
        )

        assert math.isfinite(
            item.expected_net_value
        )

        assert math.isfinite(
            item.incremental_value
        )

        expected_gross = (
            item.recovery_probability
            * amount
        )

        assert math.isclose(
            item.expected_gross_value,
            expected_gross,
            rel_tol=1e-6,
            abs_tol=1e-6,
        )

        expected_net = (
            expected_gross
            - item.intervention_cost
            - item.incentive_cost
        )

        assert math.isclose(
            item.expected_net_value,
            expected_net,
            rel_tol=1e-6,
            abs_tol=1e-6,
        )

        if item.action != "DO_NOTHING":

            expected_incremental = (
                item.estimated_uplift
                * amount
                - item.intervention_cost
                - item.incentive_cost
            )

            assert math.isclose(
                item.incremental_value,
                expected_incremental,
                rel_tol=1e-6,
                abs_tol=1e-6,
            )

    # -------------------------------------------------
    # Ranking check
    # -------------------------------------------------

    incremental_values = [
        item.incremental_value
        for item in decision.ranked_actions
    ]

    assert incremental_values == sorted(
        incremental_values,
        reverse=True,
    )

    assert (
        decision.recommended_action
        == decision.ranked_actions[0].action
    )

    # -------------------------------------------------
    # Negative-value actions should not outrank
    # DO_NOTHING.
    # -------------------------------------------------

    do_nothing_index = next(
        index
        for index, item
        in enumerate(decision.ranked_actions)
        if item.action == "DO_NOTHING"
    )

    for index, item in enumerate(
        decision.ranked_actions
    ):
        if item.incremental_value < 0:
            assert index > do_nothing_index

    print(
        "All uplift-aware DecisionEngine "
        "checks passed."
    )


if __name__ == "__main__":
    main()