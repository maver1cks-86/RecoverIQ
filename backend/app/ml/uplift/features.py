"""Feature definitions for action-specific uplift models."""

UPLIFT_NUMERIC_FEATURES = [
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

UPLIFT_CATEGORICAL_FEATURES = [
    "payment_method",
    "failure_code",
    "failure_type",
]

UPLIFT_FEATURES = (
    UPLIFT_NUMERIC_FEATURES
    + UPLIFT_CATEGORICAL_FEATURES
)
