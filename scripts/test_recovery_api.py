import json

import requests


URL = (
    "http://127.0.0.1:8000"
    "/recovery/evaluate"
)


payload = {
    "context": {
        "amount": 2500.0,

        "payment_method": "UPI",

        "failure_code": "BANK_TIMEOUT",

        "failure_type":
            "TEMPORARY_BANK_FAILURE",

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

        "customer_contact_count": 1,
    },

    "policy": {
        "max_retry_attempts": 3,

        "max_customer_contacts": 3,

        "incentives_enabled": False,

        "human_escalation_enabled": True,

        "max_incentive_amount": 500.0,

        "min_amount_for_human_escalation":
            1000.0,
    },
}


def main():

    print(
        "\nCalling RecoverIQ API..."
    )

    response = requests.post(
        URL,
        json=payload,
        timeout=30,
    )

    print(
        "Status code:",
        response.status_code,
    )

    print(
        "\nResponse:\n"
    )

    print(
        json.dumps(
            response.json(),
            indent=2,
        )
    )

    assert (
        response.status_code
        == 200
    )

    data = response.json()

    assert (
        "recommended_action"
        in data
    )

    assert (
        "ranked_actions"
        in data
    )

    assert (
        "policy_decisions"
        in data
    )

    assert (
        data[
            "recommended_action"
        ]
        == "ALTERNATE_METHOD"
    )

    policy_map = {
        item["action"]:
            item
        for item
        in data[
            "policy_decisions"
        ]
    }

    assert (
        policy_map[
            "RETRY_LATER"
        ][
            "allowed"
        ]
        is False
    )

    assert (
        policy_map[
            "INCENTIVE"
        ][
            "allowed"
        ]
        is False
    )

    assert (
        policy_map[
            "DO_NOTHING"
        ][
            "allowed"
        ]
        is True
    )

    print(
        "\nAll API sanity "
        "checks passed."
    )


if __name__ == "__main__":
    main()