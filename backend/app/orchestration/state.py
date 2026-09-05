from __future__ import annotations

from typing import Any, TypedDict


class RecoveryWorkflowState(TypedDict, total=False):
    payment_id: int
    recovery_batch_id: int | None
    optimization_assignment_id: int | None
    planned_action: str | None
    planned_policy_status: str | None
    planned_probability: float | None
    planned_expected_value: float | None
    planned_incremental_value: float | None
    planned_intervention_cost: float
    planned_incentive_cost: float
    merchant_id: int | None
    decision_id: int | None
    intervention_id: int | None

    context: dict[str, Any]
    selected_action: str | None
    policy_status: str | None

    predicted_probability: float | None
    expected_value: float | None
    incremental_value: float | None
    intervention_cost: float
    incentive_cost: float

    execution_status: str | None
    provider: str | None
    provider_action_id: str | None
    provider_status: str | None
    payment_url: str | None

    retry_count: int
    max_retries: int

    error: str | None
    next_step: str | None
