from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from app.schemas.optimization import OptimizationConstraintsRequest


class DemoBatchRequest(BaseModel):
    payment_count: int = Field(default=20, ge=1, le=1000)
    reference_id: str | None = Field(default=None, min_length=3, max_length=120)


class BatchOptimizeRequest(BaseModel):
    constraints: OptimizationConstraintsRequest = Field(default_factory=OptimizationConstraintsRequest)


class BatchResponse(BaseModel):
    id: int
    merchant_id: int
    reference_id: str
    source: str
    status: str
    payment_count: int
    revenue_at_risk: Decimal
    error_message: str | None
    created_at: datetime
    planning_started_at: datetime | None
    planning_completed_at: datetime | None
    execution_started_at: datetime | None
    execution_completed_at: datetime | None


class JobAccepted(BaseModel):
    batch_id: int
    status: str
    task_id: str | None = None


class AssignmentResponse(BaseModel):
    id: int
    payment_id: int
    amount: Decimal
    failure_reason: str | None
    selected_action: str
    policy_status: str
    recovery_probability: float
    expected_value: Decimal
    incremental_value: Decimal
    intervention_cost: Decimal
    incentive_cost: Decimal
    execution_status: str
    provider: str | None
    provider_action_id: str | None
    provider_status: str | None
    payment_url: str | None
    standalone_best_action: str | None
    selected_rank: int | None
    portfolio_agreement: bool | None
    alternatives: list[dict]
    policy_evidence: list[dict]


class AssignmentPage(BaseModel):
    items: list[AssignmentResponse]
    page: int
    page_size: int
    total: int


class BatchSummary(BaseModel):
    batch: BatchResponse
    plan_id: int | None
    plan_version: int | None
    solver_status: str | None
    observed_recovered_amount: Decimal
    estimated_incremental_value: Decimal
    action_allocation: dict[str, int]
    execution_counts: dict[str, int]
    constraint_utilization: list[dict]
    constraints_snapshot: dict
