from pathlib import Path
import random

import numpy as np
import pandas as pd


# =========================================================
# CONFIG
# =========================================================

SEED = 42
NUM_ROWS = 50_000

random.seed(SEED)
np.random.seed(SEED)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "recovery_events.csv"
)


PAYMENT_METHODS = [
    "UPI",
    "CARD",
    "NETBANKING",
    "WALLET",
]


FAILURE_TYPES = [
    "TEMPORARY_BANK_FAILURE",
    "INSUFFICIENT_FUNDS",
    "CUSTOMER_ACTION_REQUIRED",
    "PAYMENT_METHOD_ISSUE",
    "HARD_DECLINE",
    "NETWORK_FAILURE",
    "UNKNOWN",
]


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


# =========================================================
# FAILURE CODES
# =========================================================

FAILURE_CODES = {
    "TEMPORARY_BANK_FAILURE": [
        "BANK_SERVER_DOWN",
        "BANK_TIMEOUT",
        "BANK_TEMP_UNAVAILABLE",
    ],

    "INSUFFICIENT_FUNDS": [
        "INSUFFICIENT_BALANCE",
        "LOW_BALANCE",
    ],

    "CUSTOMER_ACTION_REQUIRED": [
        "OTP_FAILED",
        "AUTHENTICATION_PENDING",
        "USER_CANCELLED",
    ],

    "PAYMENT_METHOD_ISSUE": [
        "CARD_EXPIRED",
        "CARD_BLOCKED",
        "METHOD_UNAVAILABLE",
    ],

    "HARD_DECLINE": [
        "FRAUD_DECLINE",
        "ACCOUNT_BLOCKED",
        "INVALID_ACCOUNT",
    ],

    "NETWORK_FAILURE": [
        "NETWORK_TIMEOUT",
        "GATEWAY_TIMEOUT",
        "CONNECTION_FAILED",
    ],

    "UNKNOWN": [
        "UNKNOWN_ERROR",
    ],
}


# =========================================================
# ACTION COSTS
# =========================================================

ACTION_COSTS = {
    "RETRY_NOW": 0.30,
    "RETRY_LATER": 0.30,
    "PAYMENT_LINK": 0.50,
    "ALTERNATE_METHOD": 0.40,
    "WHATSAPP": 0.80,
    "EMAIL": 0.10,
    "INCENTIVE": 1.00,
    "HUMAN_ESCALATION": 25.00,
    "DO_NOTHING": 0.00,
}


# =========================================================
# BASE RECOVERY PROBABILITY
# =========================================================

BASE_RECOVERY = {
    "TEMPORARY_BANK_FAILURE": 0.40,
    "INSUFFICIENT_FUNDS": 0.22,
    "CUSTOMER_ACTION_REQUIRED": 0.32,
    "PAYMENT_METHOD_ISSUE": 0.26,
    "HARD_DECLINE": 0.05,
    "NETWORK_FAILURE": 0.38,
    "UNKNOWN": 0.18,
}


# =========================================================
# ACTION EFFECTS
#
# This encodes the simulated recovery environment.
# Positive number -> action tends to help.
# Negative number -> action tends to hurt.
# =========================================================

ACTION_EFFECTS = {
    "TEMPORARY_BANK_FAILURE": {
        "RETRY_NOW": 0.08,
        "RETRY_LATER": 0.28,
        "PAYMENT_LINK": 0.05,
        "ALTERNATE_METHOD": 0.08,
        "WHATSAPP": 0.03,
        "EMAIL": 0.01,
        "INCENTIVE": 0.04,
        "HUMAN_ESCALATION": 0.06,
        "DO_NOTHING": -0.10,
    },

    "INSUFFICIENT_FUNDS": {
        "RETRY_NOW": -0.08,
        "RETRY_LATER": 0.18,
        "PAYMENT_LINK": 0.06,
        "ALTERNATE_METHOD": 0.12,
        "WHATSAPP": 0.15,
        "EMAIL": 0.06,
        "INCENTIVE": 0.20,
        "HUMAN_ESCALATION": 0.04,
        "DO_NOTHING": -0.03,
    },

    "CUSTOMER_ACTION_REQUIRED": {
        "RETRY_NOW": -0.06,
        "RETRY_LATER": 0.02,
        "PAYMENT_LINK": 0.14,
        "ALTERNATE_METHOD": 0.05,
        "WHATSAPP": 0.25,
        "EMAIL": 0.11,
        "INCENTIVE": 0.10,
        "HUMAN_ESCALATION": 0.15,
        "DO_NOTHING": -0.10,
    },

    "PAYMENT_METHOD_ISSUE": {
        "RETRY_NOW": -0.12,
        "RETRY_LATER": -0.03,
        "PAYMENT_LINK": 0.24,
        "ALTERNATE_METHOD": 0.30,
        "WHATSAPP": 0.08,
        "EMAIL": 0.05,
        "INCENTIVE": 0.07,
        "HUMAN_ESCALATION": 0.10,
        "DO_NOTHING": -0.08,
    },

    "HARD_DECLINE": {
        "RETRY_NOW": -0.04,
        "RETRY_LATER": -0.02,
        "PAYMENT_LINK": 0.01,
        "ALTERNATE_METHOD": 0.03,
        "WHATSAPP": 0.00,
        "EMAIL": 0.00,
        "INCENTIVE": 0.02,
        "HUMAN_ESCALATION": 0.03,
        "DO_NOTHING": 0.00,
    },

    "NETWORK_FAILURE": {
        "RETRY_NOW": 0.12,
        "RETRY_LATER": 0.24,
        "PAYMENT_LINK": 0.04,
        "ALTERNATE_METHOD": 0.07,
        "WHATSAPP": 0.02,
        "EMAIL": 0.01,
        "INCENTIVE": 0.02,
        "HUMAN_ESCALATION": 0.03,
        "DO_NOTHING": -0.08,
    },

    "UNKNOWN": {
        "RETRY_NOW": 0.04,
        "RETRY_LATER": 0.10,
        "PAYMENT_LINK": 0.08,
        "ALTERNATE_METHOD": 0.08,
        "WHATSAPP": 0.08,
        "EMAIL": 0.04,
        "INCENTIVE": 0.08,
        "HUMAN_ESCALATION": 0.08,
        "DO_NOTHING": -0.04,
    },
}


# =========================================================
# CUSTOMER GENERATION
# =========================================================

def generate_customer(customer_id: int):

    tenure_days = np.random.randint(10, 1500)

    successful_payments = np.random.poisson(8)

    failed_payments = np.random.poisson(3)

    previous_recoveries = min(
        failed_payments,
        (
            np.random.binomial(
                failed_payments,
                np.random.uniform(0.15, 0.75),
            )
            if failed_payments > 0
            else 0
        ),
    )

    total_failures = max(
        failed_payments,
        1,
    )

    historical_recovery_rate = (
        previous_recoveries
        / total_failures
    )

    avg_transaction_value = (
        np.random.lognormal(
            mean=7.2,
            sigma=0.8,
        )
    )

    avg_transaction_value = np.clip(
        avg_transaction_value,
        100,
        50_000,
    )

    whatsapp_response_rate = (
        np.random.beta(2.5, 2)
    )

    email_response_rate = (
        np.random.beta(2, 4)
    )

    retry_success_rate = (
        np.random.beta(2.5, 2.5)
    )

    payment_link_conversion_rate = (
        np.random.beta(2, 2.5)
    )

    price_sensitivity = (
        np.random.beta(2, 2)
    )

    return {
        "customer_id":
            customer_id,

        "customer_tenure_days":
            tenure_days,

        "successful_payments":
            successful_payments,

        "failed_payments":
            failed_payments,

        "previous_recoveries":
            previous_recoveries,

        "historical_recovery_rate":
            historical_recovery_rate,

        "avg_transaction_value":
            avg_transaction_value,

        "whatsapp_response_rate":
            whatsapp_response_rate,

        "email_response_rate":
            email_response_rate,

        "retry_success_rate":
            retry_success_rate,

        "payment_link_conversion_rate":
            payment_link_conversion_rate,

        "price_sensitivity":
            price_sensitivity,
    }


# =========================================================
# PAYMENT GENERATION
# =========================================================

def generate_payment():

    amount = np.random.lognormal(
        mean=7.4,
        sigma=0.9,
    )

    amount = float(
        np.clip(
            amount,
            100,
            100_000,
        )
    )

    payment_method = np.random.choice(
        PAYMENT_METHODS,
        p=[
            0.55,
            0.25,
            0.12,
            0.08,
        ],
    )

    failure_type = np.random.choice(
        FAILURE_TYPES,
        p=[
            0.20,
            0.20,
            0.14,
            0.12,
            0.08,
            0.20,
            0.06,
        ],
    )

    failure_code = np.random.choice(
        FAILURE_CODES[failure_type]
    )

    attempt_number = np.random.choice(
        [1, 2, 3, 4],
        p=[
            0.60,
            0.25,
            0.10,
            0.05,
        ],
    )

    hour = np.random.randint(
        0,
        24,
    )

    day_of_week = np.random.randint(
        0,
        7,
    )

    return {
        "amount":
            amount,

        "payment_method":
            payment_method,

        "failure_type":
            failure_type,

        "failure_code":
            failure_code,

        "attempt_number":
            attempt_number,

        "hour":
            hour,

        "day_of_week":
            day_of_week,
    }


# =========================================================
# ACTION GENERATION
# =========================================================

def choose_action():

    return np.random.choice(
        ACTIONS,
        p=[
            0.14,
            0.18,
            0.11,
            0.08,
            0.14,
            0.09,
            0.08,
            0.04,
            0.14,
        ],
    )


# =========================================================
# RECOVERY PROBABILITY
# =========================================================

def calculate_recovery_probability(
    customer,
    payment,
    action,
    add_noise=True,
):

    failure_type = (
        payment["failure_type"]
    )

    probability = (
        BASE_RECOVERY[
            failure_type
        ]
    )

    probability += (
        ACTION_EFFECTS[
            failure_type
        ][action]
    )

    # -----------------------------------------------------
    # Customer recovery history
    # -----------------------------------------------------

    probability += (
        customer[
            "historical_recovery_rate"
        ]
        - 0.4
    ) * 0.20

    # -----------------------------------------------------
    # Action-specific customer affinity
    # -----------------------------------------------------

    if action == "WHATSAPP":
        probability += (
            customer[
                "whatsapp_response_rate"
            ]
            - 0.5
        ) * 0.25

    if action == "EMAIL":
        probability += (
            customer[
                "email_response_rate"
            ]
            - 0.4
        ) * 0.15

    if action in [
        "RETRY_NOW",
        "RETRY_LATER",
    ]:
        probability += (
            customer[
                "retry_success_rate"
            ]
            - 0.5
        ) * 0.20

    if action == "PAYMENT_LINK":
        probability += (
            customer[
                "payment_link_conversion_rate"
            ]
            - 0.5
        ) * 0.20

    # -----------------------------------------------------
    # Incentive effect
    # -----------------------------------------------------

    if action == "INCENTIVE":
        probability += (
            customer[
                "price_sensitivity"
            ]
            * 0.18
        )

    # -----------------------------------------------------
    # Retry fatigue
    # -----------------------------------------------------

    if (
        action
        in [
            "RETRY_NOW",
            "RETRY_LATER",
        ]
        and payment[
            "attempt_number"
        ] > 1
    ):
        probability -= (
            payment[
                "attempt_number"
            ]
            - 1
        ) * 0.06

    # -----------------------------------------------------
    # Loyal customers recover more easily
    # -----------------------------------------------------

    if (
        customer[
            "successful_payments"
        ]
        >= 10
    ):
        probability += 0.05

    # -----------------------------------------------------
    # New customers slightly less predictable
    # -----------------------------------------------------

    if (
        customer[
            "customer_tenure_days"
        ]
        < 30
    ):
        probability -= 0.04

    # -----------------------------------------------------
    # Expensive transactions slightly harder to recover
    # -----------------------------------------------------

    if (
        payment["amount"]
        > 20_000
    ):
        probability -= 0.05

    # -----------------------------------------------------
    # Timing effects
    # -----------------------------------------------------

    if (
        action
        == "RETRY_LATER"
        and payment[
            "failure_type"
        ]
        in [
            "TEMPORARY_BANK_FAILURE",
            "NETWORK_FAILURE",
        ]
    ):
        probability += 0.05

    # -----------------------------------------------------
    # Random individual noise
    #
    # Dataset generation:
    #     add_noise=True
    #
    # Policy evaluation:
    #     add_noise=False
    # -----------------------------------------------------

    if add_noise:
        probability += np.random.normal(
            0,
            0.035,
        )

    # IMPORTANT:
    # This return must be outside the add_noise block.
    return float(
        np.clip(
            probability,
            0.01,
            0.95,
        )
    )


# =========================================================
# INCENTIVE
# =========================================================

def calculate_incentive(
    action,
    amount,
):

    if action != "INCENTIVE":
        return 0.0

    incentive = min(
        amount * 0.05,
        500,
    )

    return float(incentive)


# =========================================================
# GENERATE DATASET
# =========================================================

def generate_dataset():

    print(
        f"Generating {NUM_ROWS:,} "
        f"recovery events..."
    )

    number_of_customers = 8_000

    customers = [
        generate_customer(i)
        for i in range(
            1,
            number_of_customers + 1,
        )
    ]

    rows = []

    for payment_id in range(
        1,
        NUM_ROWS + 1,
    ):

        customer = random.choice(
            customers
        )

        payment = generate_payment()

        action = choose_action()

        recovery_probability = (
            calculate_recovery_probability(
                customer,
                payment,
                action,
            )
        )

        recovered = (
            np.random.random()
            < recovery_probability
        )

        intervention_cost = (
            ACTION_COSTS[action]
        )

        incentive_cost = (
            calculate_incentive(
                action,
                payment["amount"],
            )
        )

        if recovered:

            recovered_amount = (
                payment["amount"]
            )

            recovery_time_hours = float(
                np.random.gamma(
                    shape=2,
                    scale=4,
                )
            )

        else:

            recovered_amount = 0.0

            recovery_time_hours = np.nan

        row = {
            "payment_id":
                payment_id,

            "customer_id":
                customer["customer_id"],

            "merchant_id":
                1,

            "amount":
                round(
                    payment["amount"],
                    2,
                ),

            "payment_method":
                payment["payment_method"],

            "failure_code":
                payment["failure_code"],

            "failure_type":
                payment["failure_type"],

            "attempt_number":
                payment["attempt_number"],

            "hour":
                payment["hour"],

            "day_of_week":
                payment["day_of_week"],

            "customer_tenure_days":
                customer[
                    "customer_tenure_days"
                ],

            "successful_payments":
                customer[
                    "successful_payments"
                ],

            "failed_payments":
                customer[
                    "failed_payments"
                ],

            "previous_recoveries":
                customer[
                    "previous_recoveries"
                ],

            "historical_recovery_rate":
                round(
                    customer[
                        "historical_recovery_rate"
                    ],
                    4,
                ),

            "avg_transaction_value":
                round(
                    customer[
                        "avg_transaction_value"
                    ],
                    2,
                ),

            "whatsapp_response_rate":
                round(
                    customer[
                        "whatsapp_response_rate"
                    ],
                    4,
                ),

            "email_response_rate":
                round(
                    customer[
                        "email_response_rate"
                    ],
                    4,
                ),

            "retry_success_rate":
                round(
                    customer[
                        "retry_success_rate"
                    ],
                    4,
                ),

            "payment_link_conversion_rate":
                round(
                    customer[
                        "payment_link_conversion_rate"
                    ],
                    4,
                ),

            "price_sensitivity":
                round(
                    customer[
                        "price_sensitivity"
                    ],
                    4,
                ),

            "action_taken":
                action,

            "intervention_cost":
                intervention_cost,

            "incentive_cost":
                round(
                    incentive_cost,
                    2,
                ),

            "true_recovery_probability":
                round(
                    recovery_probability,
                    4,
                ),

            "recovered":
                int(recovered),

            "recovered_amount":
                round(
                    recovered_amount,
                    2,
                ),

            "recovery_time_hours":
                (
                    round(
                        recovery_time_hours,
                        2,
                    )
                    if recovered
                    else np.nan
                ),
        }

        rows.append(row)

    return pd.DataFrame(rows)


# =========================================================
# VALIDATION
# =========================================================

def validate_dataset(df):

    print(
        "\nValidating dataset..."
    )

    assert len(df) == NUM_ROWS

    assert df[
        "payment_id"
    ].is_unique

    assert (
        df["amount"] > 0
    ).all()

    assert df[
        "true_recovery_probability"
    ].between(
        0,
        1,
    ).all()

    assert set(
        df["action_taken"].unique()
    ).issubset(
        set(ACTIONS)
    )

    assert set(
        df["failure_type"].unique()
    ).issubset(
        set(FAILURE_TYPES)
    )

    assert set(
        df["recovered"].unique()
    ).issubset(
        {0, 1}
    )

    print(
        "Validation passed."
    )


# =========================================================
# REPORTING
# =========================================================

def print_statistics(df):

    print(
        "\n=============================="
    )
    print(
        "DATASET SUMMARY"
    )
    print(
        "=============================="
    )

    print(
        f"Rows: {len(df):,}"
    )

    print(
        f"Customers: "
        f"{df['customer_id'].nunique():,}"
    )

    print(
        f"Average payment amount: "
        f"₹{df['amount'].mean():,.2f}"
    )

    print(
        f"Overall recovery rate: "
        f"{df['recovered'].mean():.2%}"
    )

    print(
        "\nFailure distribution:"
    )

    print(
        df["failure_type"]
        .value_counts(
            normalize=True
        )
        .mul(100)
        .round(2)
    )

    print(
        "\nAction distribution:"
    )

    print(
        df["action_taken"]
        .value_counts(
            normalize=True
        )
        .mul(100)
        .round(2)
    )

    print(
        "\nRecovery rate by action:"
    )

    print(
        df.groupby(
            "action_taken"
        )["recovered"]
        .mean()
        .sort_values(
            ascending=False
        )
        .round(3)
    )

    print(
        "\nRecovery rate by failure type:"
    )

    print(
        df.groupby(
            "failure_type"
        )["recovered"]
        .mean()
        .sort_values(
            ascending=False
        )
        .round(3)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    df = generate_dataset()

    validate_dataset(df)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print_statistics(df)

    print(
        f"\nDataset saved to:\n"
        f"{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()