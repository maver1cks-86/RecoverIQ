from dataclasses import dataclass, field

from app.decision.actions import RecoveryAction


RETRY_ACTIONS = {
    RecoveryAction.RETRY_NOW.value,
    RecoveryAction.RETRY_LATER.value,
}

CONTACT_ACTIONS = {
    RecoveryAction.WHATSAPP.value,
    RecoveryAction.EMAIL.value,
    RecoveryAction.PAYMENT_LINK.value,
    RecoveryAction.INCENTIVE.value,
    RecoveryAction.HUMAN_ESCALATION.value,
}

DEFAULT_ALLOWED_ACTIONS = {
    action.value
    for action in RecoveryAction
}


@dataclass(frozen=True)
class PolicyConfig:
    """
    Merchant-level recovery policy.

    These controls determine which recovery actions
    are allowed before the decision engine chooses
    the economically best intervention.
    """

    allowed_actions: set[str] = field(
        default_factory=lambda:
        DEFAULT_ALLOWED_ACTIONS.copy()
    )

    max_retry_attempts: int = 3

    max_customer_contacts: int = 3

    incentives_enabled: bool = True

    human_escalation_enabled: bool = True

    max_incentive_amount: float = 500.0

    min_amount_for_human_escalation: float = 1000.0

    approval_required_actions: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    allowed: bool
    reason: str
    requires_approval: bool = False


class PolicyEngine:

    def evaluate_action(
        self,
        action: str,
        context: dict,
        policy: PolicyConfig,
    ) -> PolicyDecision:
        """
        Determine whether a recovery action is
        permitted under merchant policy and
        operational guardrails.
        """

        # ----------------------------------------
        # DO_NOTHING is always safe and feasible.
        # ----------------------------------------

        if action == RecoveryAction.DO_NOTHING.value:
            return PolicyDecision(
                action=action,
                allowed=True,
                reason="DO_NOTHING is always allowed.",
            )

        # ----------------------------------------
        # Merchant-level allow list
        # ----------------------------------------

        if action not in policy.allowed_actions:
            return PolicyDecision(
                action=action,
                allowed=False,
                reason=(
                    "Action is disabled by "
                    "merchant policy."
                ),
            )

        failure_type = context.get(
            "failure_type"
        )

        attempt_number = int(
            context.get(
                "attempt_number",
                1,
            )
        )

        customer_contact_count = int(
            context.get(
                "customer_contact_count",
                0,
            )
        )

        amount = float(
            context.get(
                "amount",
                0.0,
            )
        )

        # ----------------------------------------
        # Hard declines should not be retried
        # automatically.
        # ----------------------------------------

        if (
            failure_type == "HARD_DECLINE"
            and action in RETRY_ACTIONS
        ):
            return PolicyDecision(
                action=action,
                allowed=False,
                reason=(
                    "Automatic retries are blocked "
                    "for HARD_DECLINE failures."
                ),
            )

        # ----------------------------------------
        # Retry limit
        # ----------------------------------------

        if (
            action in RETRY_ACTIONS
            and attempt_number
            >= policy.max_retry_attempts
        ):
            return PolicyDecision(
                action=action,
                allowed=False,
                reason=(
                    "Maximum retry attempts "
                    "have been reached."
                ),
            )

        # ----------------------------------------
        # Customer contact frequency cap
        # ----------------------------------------

        if (
            action in CONTACT_ACTIONS
            and customer_contact_count
            >= policy.max_customer_contacts
        ):
            return PolicyDecision(
                action=action,
                allowed=False,
                reason=(
                    "Customer contact limit "
                    "has been reached."
                ),
            )

        # ----------------------------------------
        # Incentive policy
        # ----------------------------------------

        if (
            action
            == RecoveryAction.INCENTIVE.value
        ):

            if not policy.incentives_enabled:
                return PolicyDecision(
                    action=action,
                    allowed=False,
                    reason=(
                        "Incentives are disabled "
                        "by merchant policy."
                    ),
                )

            incentive_amount = min(
                amount * 0.05,
                500.0,
            )

            if (
                incentive_amount
                > policy.max_incentive_amount
            ):
                return PolicyDecision(
                    action=action,
                    allowed=False,
                    reason=(
                        "Required incentive exceeds "
                        "merchant incentive limit."
                    ),
                )

        # ----------------------------------------
        # Human escalation policy
        # ----------------------------------------

        if (
            action
            == RecoveryAction.HUMAN_ESCALATION.value
        ):

            if (
                not
                policy.human_escalation_enabled
            ):
                return PolicyDecision(
                    action=action,
                    allowed=False,
                    reason=(
                        "Human escalation is "
                        "disabled by merchant policy."
                    ),
                )

            if (
                amount
                < policy.min_amount_for_human_escalation
            ):
                return PolicyDecision(
                    action=action,
                    allowed=False,
                    reason=(
                        "Payment amount is below "
                        "the human-escalation threshold."
                    ),
                )

        # ----------------------------------------
        # Passed all policy checks
        # ----------------------------------------

        requires_approval = action in policy.approval_required_actions
        return PolicyDecision(
            action=action,
            allowed=True,
            reason=(
                "Action requires merchant approval before execution."
                if requires_approval
                else "Action passed all policy checks."
            ),
            requires_approval=requires_approval,
        )

    def filter_actions(
        self,
        actions: list[str],
        context: dict,
        policy: PolicyConfig,
    ) -> tuple[list[str], list[PolicyDecision]]:
        """
        Evaluate multiple actions and return:

        1. allowed action names
        2. policy decision/audit records
        """

        decisions = [
            self.evaluate_action(
                action=action,
                context=context,
                policy=policy,
            )
            for action in actions
        ]

        allowed_actions = [
            decision.action
            for decision in decisions
            if decision.allowed
        ]

        return (
            allowed_actions,
            decisions,
        )
