from pydantic import BaseModel, Field
from typing import Optional


class RecoveryContextRequest(BaseModel):
    amount: float = Field(gt=0)

    payment_method: str
    failure_code: str
    failure_type: str

    attempt_number: int = Field(ge=1)

    hour: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)

    customer_tenure_days: int = Field(ge=0)

    successful_payments: int = Field(ge=0)
    failed_payments: int = Field(ge=0)
    previous_recoveries: int = Field(ge=0)

    historical_recovery_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    avg_transaction_value: float = Field(
        ge=0.0
    )

    whatsapp_response_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    email_response_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    retry_success_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    payment_link_conversion_rate: float = Field(
        ge=0.0,
        le=1.0,
    )

    price_sensitivity: float = Field(
        ge=0.0,
        le=1.0,
    )

    customer_contact_count: int = Field(
        default=0,
        ge=0,
    )


class RecoveryPolicyRequest(BaseModel):
    max_retry_attempts: int = Field(
        default=3,
        ge=1,
    )

    max_customer_contacts: int = Field(
        default=3,
        ge=0,
    )

    incentives_enabled: bool = True

    human_escalation_enabled: bool = True

    max_incentive_amount: float = Field(
        default=500.0,
        ge=0.0,
    )

    min_amount_for_human_escalation: float = Field(
        default=1000.0,
        ge=0.0,
    )

    allowed_actions: Optional[list[str]] = None


class RecoveryEvaluationRequest(BaseModel):
    context: RecoveryContextRequest

    policy: Optional[
        RecoveryPolicyRequest
    ] = None


class RankedActionResponse(BaseModel):
    action: str

    recovery_probability: float

    intervention_cost: float

    incentive_cost: float

    expected_gross_value: float

    expected_net_value: float

    incremental_value: float


class PolicyDecisionResponse(BaseModel):
    action: str
    allowed: bool
    reason: str
    requires_approval: bool = False


class RecoveryEvaluationResponse(BaseModel):
    recommended_action: str

    recovery_probability: float

    expected_net_value: float

    incremental_value: float

    ranked_actions: list[
        RankedActionResponse
    ]

    policy_decisions: list[
        PolicyDecisionResponse
    ]
