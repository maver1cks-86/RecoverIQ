from pydantic import BaseModel, Field, field_validator

from app.decision.actions import RecoveryAction


class OptimizationConstraintsRequest(BaseModel):
    total_budget: float = Field(default=2000, ge=0)
    incentive_budget: float = Field(default=1000, ge=0)
    max_retries: int = Field(default=350, ge=0)
    max_contacts: int = Field(default=300, ge=0)
    max_whatsapp: int = Field(default=150, ge=0)
    max_incentive_actions: int = Field(default=50, ge=0)
    max_human_escalations: int = Field(default=30, ge=0)
    solver_timeout_ms: int = Field(default=30000, ge=1000, le=120000)
    enabled_actions: list[RecoveryAction] | None = None

    @field_validator("enabled_actions")
    @classmethod
    def require_do_nothing_when_actions_are_limited(
        cls,
        value: list[RecoveryAction] | None,
    ) -> list[RecoveryAction] | None:
        if value is None:
            return None
        unique = list(dict.fromkeys(value))
        if RecoveryAction.DO_NOTHING not in unique:
            raise ValueError("enabled_actions must include DO_NOTHING")
        return unique


class PortfolioMetadataResponse(BaseModel):
    source: str
    label: str
    payment_count: int
    revenue_at_risk: float
    default_constraints: OptimizationConstraintsRequest


class ResourceUsage(BaseModel):
    key: str
    label: str
    used: float
    limit: float
    unit: str
    within_constraint: bool


class AlternativeScore(BaseModel):
    action: str
    recovery_probability: float
    incremental_value: float
    intervention_cost: float
    expected_net_value: float


class PlanAssignment(BaseModel):
    payment_id: str
    amount: float
    payment_method: str
    failure_type: str
    action: str
    recovery_probability: float
    incremental_value: float
    intervention_cost: float
    incentive_cost: float
    expected_net_value: float
    policy_status: str
    alternatives: list[AlternativeScore]


class ActionAllocation(BaseModel):
    action: str
    count: int
    percentage: float
    incremental_value: float


class OptimizationRunResponse(BaseModel):
    portfolio_source: str
    portfolio_label: str
    status: str
    payment_count: int
    revenue_at_risk: float
    baseline_net_value: float
    baseline_recovery_rate: float
    optimized_net_value: float
    total_incremental_value: float
    improvement_amount: float
    improvement_percent: float
    expected_recovery_rate: float
    intervention_spend: float
    action_allocation: list[ActionAllocation]
    resource_usage: list[ResourceUsage]
    assignments: list[PlanAssignment]
