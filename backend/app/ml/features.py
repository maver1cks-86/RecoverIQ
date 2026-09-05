NUMERIC_FEATURES = [
    "amount",
    "attempt_number",
    "hour",
    "day_of_week",

    "customer_tenure_days",
    "successful_payments",
    "failed_payments",
    "previous_recoveries",
    "historical_recovery_rate",
    "avg_transaction_value",

    "whatsapp_response_rate",
    "email_response_rate",
    "retry_success_rate",
    "payment_link_conversion_rate",
    "price_sensitivity",
]


CATEGORICAL_FEATURES = [
    "payment_method",
    "failure_code",
    "failure_type",
    "action_taken",
]


MODEL_FEATURES = (
    NUMERIC_FEATURES
    + CATEGORICAL_FEATURES
)


TARGET = "recovered"


LEAKAGE_COLUMNS = [
    "true_recovery_probability",
    "recovered_amount",
    "recovery_time_hours",
    "intervention_cost",
    "incentive_cost",
]


IDENTIFIER_COLUMNS = [
    "payment_id",
    "customer_id",
    "merchant_id",
]