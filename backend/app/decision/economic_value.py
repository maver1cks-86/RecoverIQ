from dataclasses import dataclass

from app.decision.actions import RecoveryAction


INTERVENTION_COSTS = {
    RecoveryAction.RETRY_NOW: 0.30,
    RecoveryAction.RETRY_LATER: 0.30,
    RecoveryAction.PAYMENT_LINK: 0.50,
    RecoveryAction.ALTERNATE_METHOD: 0.40,
    RecoveryAction.WHATSAPP: 0.80,
    RecoveryAction.EMAIL: 0.10,
    RecoveryAction.INCENTIVE: 1.00,
    RecoveryAction.HUMAN_ESCALATION: 25.00,
    RecoveryAction.DO_NOTHING: 0.00,
}


@dataclass(frozen=True)
class EconomicValue:
    action: str
    recovery_probability: float
    estimated_uplift: float
    intervention_cost: float
    incentive_cost: float
    expected_gross_value: float
    expected_net_value: float
    incremental_value: float = 0.0


def calculate_incentive_cost(
    action: str,
    amount: float,
) -> float:
    """
    Calculate incentive cost for an action.

    Incentive is modeled as 5% of transaction value,
    capped at Rs. 500.
    """

    if action != RecoveryAction.INCENTIVE.value:
        return 0.0

    return float(
        min(
            amount * 0.05,
            500.0,
        )
    )


def calculate_economic_value(
    action: str,
    recovery_probability: float,
    estimated_uplift: float,
    amount: float,
) -> EconomicValue:
    """
    Calculate predictive and incremental economic
    value for a candidate recovery action.

    Predictive expected gross value:

        P(recovery | action) * payment amount

    Predictive expected net value:

        expected gross value
        - intervention cost
        - incentive cost

    Uplift-aware incremental value:

        estimated_uplift * payment amount
        - intervention cost
        - incentive cost

    DO_NOTHING is the control action, so its
    incremental value is exactly zero.
    """

    action_enum = RecoveryAction(action)

    intervention_cost = float(
        INTERVENTION_COSTS[
            action_enum
        ]
    )

    incentive_cost = (
        calculate_incentive_cost(
            action=action,
            amount=amount,
        )
    )

    # -------------------------------------------------
    # Predictive expected value
    # -------------------------------------------------

    expected_gross_value = (
        recovery_probability
        * amount
    )

    expected_net_value = (
        expected_gross_value
        - intervention_cost
        - incentive_cost
    )

    # -------------------------------------------------
    # Uplift-aware incremental value
    # -------------------------------------------------

    if action == RecoveryAction.DO_NOTHING.value:

        # DO_NOTHING is our control action.
        estimated_uplift = 0.0
        incremental_value = 0.0

    else:

        incremental_value = (
            estimated_uplift
            * amount
            - intervention_cost
            - incentive_cost
        )

    return EconomicValue(
        action=action,

        recovery_probability=float(
            recovery_probability
        ),

        estimated_uplift=float(
            estimated_uplift
        ),

        intervention_cost=float(
            intervention_cost
        ),

        incentive_cost=float(
            incentive_cost
        ),

        expected_gross_value=float(
            expected_gross_value
        ),

        expected_net_value=float(
            expected_net_value
        ),

        incremental_value=float(
            incremental_value
        ),
    )