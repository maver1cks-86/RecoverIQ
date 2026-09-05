from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.decision.actions import RecoveryAction
from app.orchestration.nodes import (
    create_intervention,
    evaluate_recovery,
    execute_intervention,
    finalize,
    handle_failure,
    load_context,
    persist_decision,
)
from app.orchestration.state import RecoveryWorkflowState


logger = logging.getLogger(__name__)


def _after_decision_persistence(state: RecoveryWorkflowState) -> str:
    if state.get("selected_action") == RecoveryAction.DO_NOTHING.value:
        return "finalize"
    return "create_intervention"


def _after_intervention_creation(state: RecoveryWorkflowState) -> str:
    return (
        "finalize"
        if state.get("next_step") == "finalize"
        else "execute_intervention"
    )


def _after_execution(state: RecoveryWorkflowState) -> str:
    return (
        "handle_failure"
        if state.get("execution_status") == "FAILED"
        else "finalize"
    )


def _after_failure(state: RecoveryWorkflowState) -> str:
    return (
        "execute_intervention"
        if state.get("next_step") == "execute_intervention"
        else "finalize"
    )


def build_recovery_graph():
    builder = StateGraph(RecoveryWorkflowState)

    builder.add_node("load_context", load_context)
    builder.add_node("evaluate_recovery", evaluate_recovery)
    builder.add_node("persist_decision", persist_decision)
    builder.add_node("create_intervention", create_intervention)
    builder.add_node("execute_intervention", execute_intervention)
    builder.add_node("handle_failure", handle_failure)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "evaluate_recovery")
    builder.add_edge("evaluate_recovery", "persist_decision")
    builder.add_conditional_edges(
        "persist_decision",
        _after_decision_persistence,
        {
            "create_intervention": "create_intervention",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "create_intervention",
        _after_intervention_creation,
        {
            "execute_intervention": "execute_intervention",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "execute_intervention",
        _after_execution,
        {
            "handle_failure": "handle_failure",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "handle_failure",
        _after_failure,
        {
            "execute_intervention": "execute_intervention",
            "finalize": "finalize",
        },
    )
    builder.add_edge("finalize", END)

    return builder.compile()


recovery_graph = build_recovery_graph()


def run_recovery_workflow(
    payment_id: int,
    max_retries: int = 2,
    *,
    planned_action: str | None = None,
    optimization_assignment_id: int | None = None,
    recovery_batch_id: int | None = None,
    planned_policy_status: str | None = None,
    planned_probability: float | None = None,
    planned_expected_value: float | None = None,
    planned_incremental_value: float | None = None,
    planned_intervention_cost: float = 0.0,
    planned_incentive_cost: float = 0.0,
) -> RecoveryWorkflowState:
    if payment_id <= 0:
        raise ValueError("payment_id must be greater than zero.")
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative.")
    if planned_action is None or optimization_assignment_id is None:
        raise ValueError(
            "A persisted optimization assignment and its planned action are required."
        )

    initial_state: RecoveryWorkflowState = {
        "payment_id": payment_id,
        "recovery_batch_id": recovery_batch_id,
        "optimization_assignment_id": optimization_assignment_id,
        "planned_action": planned_action,
        "planned_policy_status": planned_policy_status,
        "planned_probability": planned_probability,
        "planned_expected_value": planned_expected_value,
        "planned_incremental_value": planned_incremental_value,
        "planned_intervention_cost": planned_intervention_cost,
        "planned_incentive_cost": planned_incentive_cost,
        "merchant_id": None,
        "decision_id": None,
        "intervention_id": None,
        "selected_action": None,
        "policy_status": None,
        "predicted_probability": None,
        "expected_value": None,
        "incremental_value": None,
        "intervention_cost": 0.0,
        "incentive_cost": 0.0,
        "execution_status": None,
        "provider": None,
        "provider_action_id": None,
        "provider_status": None,
        "payment_url": None,
        "retry_count": 0,
        "max_retries": max_retries,
        "error": None,
        "next_step": "load_context",
    }

    logger.info(
        "recoveriq.langgraph.start assignment_id=%s payment_id=%s planned_action=%s",
        optimization_assignment_id,
        payment_id,
        planned_action,
    )
    result = recovery_graph.invoke(initial_state)
    logger.info(
        "recoveriq.langgraph.complete assignment_id=%s payment_id=%s "
        "planned_action=%s selected_action=%s execution_status=%s "
        "provider_action_id=%s",
        optimization_assignment_id,
        payment_id,
        planned_action,
        result.get("selected_action"),
        result.get("execution_status"),
        result.get("provider_action_id"),
    )
    return result
