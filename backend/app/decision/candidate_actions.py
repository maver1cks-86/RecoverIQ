ACTIONS = [
    "RETRY_NOW",
    "RETRY_LATER",
    "PAYMENT_LINK",
    "ALTERNATE_METHOD",
    "WHATSAPP",
    "EMAIL",
    "INCENTIVE",
    "HUMAN_ESCALATION",
    "DO_NOTHING",
]


def get_candidate_actions(
    context: dict,
) -> list[str]:
    return ACTIONS.copy()