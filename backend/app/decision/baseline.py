from dataclasses import dataclass


RETRY_ACTIONS = {
    "RETRY_NOW",
    "RETRY_LATER",
}

CUSTOMER_CONTACT_ACTIONS = {
    "WHATSAPP",
    "EMAIL",
    "PAYMENT_LINK",
    "INCENTIVE",
    "HUMAN_ESCALATION",
}


@dataclass(frozen=True)
class BaselineDecision:
    action: str
    reason: str


def choose_baseline_action(
    failure_type: str,
    attempt_number: int,
) -> BaselineDecision:

    if (
        failure_type in {
            "TEMPORARY_BANK_FAILURE",
            "NETWORK_FAILURE",
            "UNKNOWN",
        }
        and attempt_number >= 3
    ):
        return BaselineDecision(
            action="DO_NOTHING",
            reason="Maximum retry limit reached",
        )

    if failure_type == "TEMPORARY_BANK_FAILURE":
        return BaselineDecision(
            action="RETRY_LATER",
            reason="Temporary bank failure",
        )

    if failure_type == "NETWORK_FAILURE":
        return BaselineDecision(
            action="RETRY_LATER",
            reason="Transient network failure",
        )

    if failure_type == "INSUFFICIENT_FUNDS":
        return BaselineDecision(
            action="RETRY_LATER",
            reason="Allow time for funds to become available",
        )

    if failure_type == "CUSTOMER_ACTION_REQUIRED":
        return BaselineDecision(
            action="WHATSAPP",
            reason="Customer action required",
        )

    if failure_type == "PAYMENT_METHOD_ISSUE":
        return BaselineDecision(
            action="PAYMENT_LINK",
            reason="Original payment method has an issue",
        )

    if failure_type == "HARD_DECLINE":
        return BaselineDecision(
            action="DO_NOTHING",
            reason="Hard decline unlikely to benefit from retry",
        )

    return BaselineDecision(
        action="RETRY_LATER",
        reason="Default recovery rule",
    )