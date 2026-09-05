from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intervention import Intervention
from app.models.outcome import Outcome
from app.models.recovery_batch import OptimizationAssignment
from app.decision.actions import RecoveryAction
from app.schemas.copilot import (
    CopilotChatRequest,
    CopilotChatResponse,
    SupportingFact,
)
from app.services.audit_service import get_payment_audit
from app.services.dashboard_service import get_dashboard_overview
from app.services.llm_provider import GroundedLLMProvider
from app.services.optimization_service import (
    get_latest_optimization_assignment,
    get_latest_optimization_summary,
)


SUGGESTED = [
    "What's limiting recovery?",
    "Why are payments receiving DO_NOTHING?",
    "Show recent successful recoveries",
    "Explain why this action was selected",
]


def _fact(label: str, value: object) -> SupportingFact:
    return SupportingFact(label=label, value=str(value))


def _payment_id(request: CopilotChatRequest) -> int | None:
    if request.context and request.context.payment_id:
        return request.context.payment_id

    match = re.search(
        r"\bpayment\s*#?\s*(\d+)\b",
        request.message,
        re.I,
    )

    return int(match.group(1)) if match else None


def _payment_evidence(
    db: Session,
    payment_id: int,
) -> tuple[dict, list[SupportingFact], str]:
    audit = get_payment_audit(db, payment_id)

    if audit is None:
        return (
            {
                "payment_id": payment_id,
                "found": False,
            },
            [
                _fact(
                    "Payment",
                    f"#{payment_id} not found",
                )
            ],
            (
                f"Payment #{payment_id} was not found in the live "
                "RecoverIQ database."
            ),
        )

    decisions = [
        event
        for event in audit.events
        if event.event_type == "DECISION"
    ]

    plans = [
        event
        for event in audit.events
        if event.event_type == "PLAN"
    ]

    outcomes = [
        event
        for event in audit.events
        if event.event_type == "OUTCOME"
    ]

    webhooks = [
        event
        for event in audit.events
        if event.event_type == "WEBHOOK"
    ]

    facts = [
        _fact("Payment", f"#{payment_id}"),
        _fact("Current status", audit.current_status),
        _fact("Recorded events", len(audit.events)),
    ]

    if decisions:
        facts.append(
            _fact(
                "Selected action",
                decisions[-1].status or "Unavailable",
            )
        )

    if plans:
        latest_plan = plans[-1]
        alternatives = latest_plan.details.get("alternatives") or []
        standalone_best = latest_plan.details.get("standalone_best_action")
        selected_action = latest_plan.status
        constraints = latest_plan.details.get("constraints_snapshot") or {}
        incentive_limit = constraints.get("max_incentive_actions")
        incentive_assignments = []
        if latest_plan.details.get("plan_id") is not None:
            incentive_assignments = db.scalars(
                select(OptimizationAssignment).where(
                    OptimizationAssignment.plan_id == int(latest_plan.details["plan_id"]),
                    OptimizationAssignment.selected_action == RecoveryAction.INCENTIVE,
                )
            ).all()
        facts.extend(
            [
                _fact("Portfolio action", latest_plan.status or "Unavailable"),
                _fact("Standalone rank", latest_plan.details.get("selected_rank")),
                _fact("Policy", latest_plan.details.get("policy_status")),
                _fact(
                    "Incremental value",
                    f"₹{latest_plan.details.get('incremental_value')}",
                ),
                _fact("Plan version", latest_plan.details.get("plan_version")),
            ]
        )
        if incentive_limit is not None:
            facts.append(
                _fact(
                    "Incentive action capacity",
                    f"{len(incentive_assignments)} / {incentive_limit}",
                )
            )

    if outcomes:
        facts.append(
            _fact(
                "Outcome",
                outcomes[-1].status or "Unavailable",
            )
        )

    if webhooks:
        facts.append(
            _fact(
                "Latest webhook",
                (
                    f"{webhooks[-1].details.get('event_type')} · "
                    f"{webhooks[-1].status}"
                ),
            )
        )

    evidence = {
        "scope": audit.source,
        "payment_id": payment_id,
        "current_status": audit.current_status,
        "events": [
            event.model_dump(mode="json")
            for event in audit.events
        ],
    }

    answer = (
        f"Payment #{payment_id} is currently "
        f"{audit.current_status}. Its recovery memory contains "
        f"{len(audit.events)} persisted events."
    )

    if decisions:
        answer += (
            f" The recorded recovery action is "
            f"{decisions[-1].status}."
        )
    elif plans:
        latest_plan = plans[-1]
        answer += (
            f" Its persisted portfolio-selected action is {latest_plan.status}, "
            f"ranked #{latest_plan.details.get('selected_rank')} among independent "
            "policy-eligible candidates. This selection belongs to plan "
            f"version {latest_plan.details.get('plan_version')} and has stored "
            f"incremental value ₹{latest_plan.details.get('incremental_value')}."
        )
        if (
            standalone_best == RecoveryAction.INCENTIVE.value
            and selected_action != RecoveryAction.INCENTIVE.value
            and incentive_limit == 1
            and len(incentive_assignments) == 1
        ):
            incentive = next(
                (item for item in alternatives if item.get("action") == "INCENTIVE"),
                None,
            )
            selected = next(
                (item for item in alternatives if item.get("action") == selected_action),
                None,
            )
            gap = (
                float(incentive["incremental_value"])
                - float(selected["incremental_value"])
                if incentive and selected
                else None
            )
            answer += (
                " The binding max_incentive_actions = 1 portfolio constraint "
                f"was fully used by Payment #{incentive_assignments[0].payment_id}. "
                f"Although INCENTIVE ranked #1 locally for Payment #{payment_id}"
                + (f" by ₹{gap:.2f}," if gap is not None else ",")
                + f" the MILP selected rank #2 {selected_action} here because "
                "assigning the single incentive elsewhere produced the stronger "
                "combined portfolio objective."
            )

    if outcomes:
        answer += (
            f" The latest outcome is "
            f"{outcomes[-1].status}."
        )

    return evidence, facts, answer


def _optimization_evidence() -> tuple[
    dict,
    list[SupportingFact],
    str,
]:
    summary = get_latest_optimization_summary()

    if summary is None:
        return (
            {"available": False},
            [
                _fact(
                    "Optimization",
                    "No run in this backend process",
                )
            ],
            (
                "No demo optimization has been run in this backend "
                "process yet. Run Portfolio Optimization first."
            ),
        )

    usage = summary["resource_usage"]

    binding = [
        item
        for item in usage
        if item["limit"]
        and item["used"] >= item["limit"] - 0.01
    ]

    actions = {
        item["action"]: item["count"]
        for item in summary["action_allocation"]
    }

    facts = [
        _fact("Solver", summary["status"]),
        _fact(
            "Portfolio",
            f"{summary['payment_count']} payments",
        ),
        _fact(
            "DO_NOTHING",
            f"{actions.get('DO_NOTHING', 0)} payments",
        ),
    ]

    facts.extend(
        _fact(
            item["label"],
            f"{item['used']} / {item['limit']} {item['unit']}",
        )
        for item in binding[:4]
    )

    if binding:
        labels = ", ".join(
            item["label"]
            for item in binding
        )

        answer = (
            f"The latest demo plan is {summary['status']}. "
            f"Fully utilized resources are {labels}. "
            "These constraints are currently limiting the feasible "
            "allocation. "
            f"{actions.get('DO_NOTHING', 0)} payments received "
            "DO_NOTHING because the optimizer cannot allocate "
            "unlimited recovery resources across the portfolio."
        )

    else:
        answer = (
            f"The latest demo plan is {summary['status']} and no "
            "reported capacity is fully utilized. "
            f"{actions.get('DO_NOTHING', 0)} payments received "
            "DO_NOTHING."
        )

    return summary, facts, answer


def _assignment_evidence(
    payment_id: str,
    question: str,
) -> tuple[dict, list[SupportingFact], str]:
    assignment = get_latest_optimization_assignment(payment_id)

    if assignment is None:
        return (
            {
                "payment_id": payment_id,
                "available": False,
            },
            [
                _fact(
                    "Portfolio payment",
                    payment_id,
                ),
                _fact(
                    "Decision",
                    "No cached optimization result",
                ),
            ],
            (
                "That portfolio decision is not available in this "
                "backend process. Run Portfolio Optimization again, "
                "then reopen the decision."
            ),
        )

    alternatives = assignment["alternatives"]

    ranked_alternatives = sorted(
        alternatives,
        key=lambda item: item["incremental_value"],
        reverse=True,
    )

    best_independent = ranked_alternatives[0]

    selected_rank = next(
        (
            index + 1
            for index, item in enumerate(ranked_alternatives)
            if item["action"] == assignment["action"]
        ),
        None,
    )

    local_and_portfolio_agree = (
        best_independent["action"] == assignment["action"]
    )

    total_intervention_cost = (
        assignment["intervention_cost"]
        + assignment["incentive_cost"]
    )

    recovery_pct = (
        assignment["recovery_probability"] * 100
    )

    facts = [
        _fact(
            "Portfolio payment",
            payment_id,
        ),
        _fact(
            "Selected action",
            assignment["action"],
        ),
        _fact(
            "Predicted recovery",
            f"{recovery_pct:.2f}%",
        ),
        _fact(
            "Incremental value",
            f"₹{assignment['incremental_value']:.2f}",
        ),
        _fact(
            "Intervention cost",
            f"₹{total_intervention_cost:.2f}",
        ),
        _fact(
            "Policy",
            assignment["policy_status"],
        ),
        _fact(
            "Standalone rank",
            (
                f"#{selected_rank} of "
                f"{len(ranked_alternatives)} eligible actions"
                if selected_rank is not None
                else "Unavailable"
            ),
        ),
        _fact(
            "Local vs portfolio decision",
            (
                "Agreed"
                if local_and_portfolio_agree
                else "Portfolio tradeoff"
            ),
        ),
    ]

    #
    # CASE 1:
    # The portfolio-selected action is also the strongest
    # standalone action.
    #
    if local_and_portfolio_agree:
        answer = (
            f"{assignment['action']} was selected for Payment "
            f"{payment_id} because it was the highest-valued "
            "eligible standalone action for this payment. "
            f"The recovery model estimated a {recovery_pct:.2f}% "
            f"recovery probability under {assignment['action']}. "
            f"The intervention costs ₹{total_intervention_cost:.2f}, "
            f"and the resulting incremental value is "
            f"₹{assignment['incremental_value']:.2f}. "
            f"The policy engine marked the action "
            f"{assignment['policy_status']}. "
            "In this case, there was no portfolio-level compromise: "
            "the locally strongest action and the portfolio-selected "
            "action agreed."
        )

    #
    # CASE 2:
    # Another action scores higher locally, but the portfolio
    # optimizer selected this action.
    #
    else:
        value_gap = (
            best_independent["incremental_value"]
            - assignment["incremental_value"]
        )

        answer = (
            f"{assignment['action']} was selected for Payment "
            f"{payment_id}, even though "
            f"{best_independent['action']} had the highest standalone "
            "incremental value for this individual payment. "
            f"The selected action has a {recovery_pct:.2f}% predicted "
            f"recovery probability, costs "
            f"₹{total_intervention_cost:.2f}, and contributes "
            f"₹{assignment['incremental_value']:.2f} in incremental "
            "value. "
            f"{best_independent['action']} had a standalone "
            f"incremental value of "
            f"₹{best_independent['incremental_value']:.2f}, "
            f"which is ₹{value_gap:.2f} higher locally. "
            f"The policy engine marked {assignment['action']} "
            f"{assignment['policy_status']}. "
            "This is a portfolio-level tradeoff: RecoverIQ optimizes "
            "the combined value of all payments under shared merchant "
            "constraints rather than independently choosing the "
            "highest-scoring action for every payment."
        )

    #
    # If the user explicitly asks "Why not X?",
    # compare X with the selected action using actual stored values.
    #
    normalized = (
        question
        .upper()
        .replace(" ", "_")
        .replace("-", "_")
    )

    questioned = next(
        (
            item
            for item in alternatives
            if item["action"] in normalized
            and item["action"] != assignment["action"]
        ),
        None,
    )

    if questioned is not None:
        difference = (
            assignment["incremental_value"]
            - questioned["incremental_value"]
        )

        facts.append(
            _fact(
                f"{questioned['action']} incremental value",
                f"₹{questioned['incremental_value']:.2f}",
            )
        )

        if difference >= 0:
            answer += (
                f" Compared with {questioned['action']}, the selected "
                f"{assignment['action']} action provides "
                f"₹{difference:.2f} more incremental value for this "
                "payment based on the stored action scores."
            )

        else:
            answer += (
                f" {questioned['action']} actually scores "
                f"₹{abs(difference):.2f} higher for this payment "
                "when considered independently. Its non-selection "
                "therefore reflects the portfolio allocation rather "
                "than a better local score for the chosen action."
            )

    #
    # Add compact structured reasoning to the evidence passed to
    # the optional LLM. This keeps generated explanations grounded.
    #
    evidence = {
        **assignment,
        "decision_interpretation": {
            "selected_action": assignment["action"],
            "standalone_best_action": best_independent["action"],
            "selected_standalone_rank": selected_rank,
            "eligible_action_count": len(ranked_alternatives),
            "local_and_portfolio_agree": local_and_portfolio_agree,
            "selected_incremental_value": assignment[
                "incremental_value"
            ],
            "standalone_best_incremental_value": best_independent[
                "incremental_value"
            ],
            "policy_status": assignment["policy_status"],
            "predicted_recovery_percent": recovery_pct,
            "total_intervention_cost": total_intervention_cost,
            "grounded_explanation": answer,
        },
    }

    return evidence, facts, answer


def _recent_recoveries(
    db: Session,
) -> tuple[dict, list[SupportingFact], str]:
    rows = db.execute(
        select(Outcome, Intervention)
        .join(Intervention)
        .where(Outcome.recovered.is_(True))
        .order_by(Outcome.completed_at.desc())
        .limit(5)
    ).all()

    compact = [
        {
            "payment_id": intervention.decision.payment_id,
            "amount": str(outcome.recovered_amount),
            "action": intervention.action_type.value,
            "completed_at": outcome.completed_at,
        }
        for outcome, intervention in rows
    ]

    facts = [
        _fact(
            f"Payment #{item['payment_id']}",
            f"₹{item['amount']} · {item['action']}",
        )
        for item in compact
    ]

    answer = (
        f"I found {len(compact)} recent successful recoveries "
        "in the live database."
        if compact
        else (
            "No successful recoveries are currently persisted "
            "in the live database."
        )
    )

    return {
        "scope": "LIVE_SYSTEM_DATABASE",
        "recoveries": compact,
    }, facts, answer


def answer_copilot(
    db: Session,
    request: CopilotChatRequest,
) -> CopilotChatResponse:
    message = request.message.lower()

    payment_id = _payment_id(request)

    optimization_payment_id = (
        request.context.optimization_payment_id
        if request.context
        else None
    )

    #
    # Optimizer decision explanation
    #
    if optimization_payment_id is not None:
        evidence, facts, deterministic = _assignment_evidence(
            optimization_payment_id,
            request.message,
        )

        tools = [
            "get_optimization_assignment",
        ]

        scope = "NON-PERSISTED DEMO PORTFOLIO OPTIMIZATION"

        #
        # Decision explanations must remain deterministic because
        # they directly explain financial optimization results.
        #
        # We still instantiate the LLM provider so the UI can report
        # whether AI is available, but the grounded backend explanation
        # remains the source of truth.
        #
        provider = GroundedLLMProvider()

        return CopilotChatResponse(
            answer=deterministic,
            facts=facts[:10],
            tools_used=tools,
            suggested_questions=[
                "Why was this action selected?",
                "Was this the best standalone action?",
                "Why not INCENTIVE?",
                "Did portfolio constraints affect this decision?",
            ],
            ai_available=provider.configured,
            data_scope=scope,
        )

    #
    # Live payment recovery / audit
    #
    elif payment_id is not None:
        evidence, facts, deterministic = _payment_evidence(
            db,
            payment_id,
        )

        tools = [
            "get_audit_trace",
            "get_payment_recovery_history",
        ]

        scope = "LIVE SYSTEM / DATABASE DATA"

    #
    # Portfolio constraint / resource questions
    #
    elif any(
        word in message
        for word in (
            "limit",
            "constraint",
            "budget",
            "do_nothing",
            "do nothing",
            "most-used",
            "most used",
        )
    ):
        evidence, facts, deterministic = (
            _optimization_evidence()
        )

        tools = [
            "get_optimization_summary",
            "get_constraint_utilization",
            "get_action_distribution",
        ]

        scope = "NON-PERSISTED DEMO PORTFOLIO OPTIMIZATION"

    #
    # Recent successful live recoveries
    #
    elif (
        "recent" in message
        and (
            "recover" in message
            or "success" in message
        )
    ):
        evidence, facts, deterministic = _recent_recoveries(
            db,
        )

        tools = [
            "get_recent_recoveries",
        ]

        scope = "LIVE SYSTEM / DATABASE DATA"

    #
    # Frozen offline evaluation fallback
    #
    else:
        dashboard = get_dashboard_overview(db)

        evidence = {
            "scope": "FROZEN_OFFLINE_EVALUATION",
            "evaluation": (
                dashboard.offline_evaluation.model_dump(
                    mode="json"
                )
            ),
        }

        optimized = next(
            item
            for item in dashboard.offline_evaluation.strategies
            if item.strategy == "OPTIMIZED"
        )

        facts = [
            _fact(
                "Evaluation scope",
                "Frozen 10,000-payment held-out test set",
            ),
            _fact(
                "Constrained improvement",
                (
                    f"₹{optimized.uplift_amount} · "
                    f"+{optimized.uplift_percent:.2f}%"
                ),
            ),
            _fact(
                "Solver",
                dashboard.offline_evaluation.solver_status,
            ),
        ]

        deterministic = (
            "On the frozen 10,000-payment held-out evaluation, "
            f"constrained RecoverIQ improved net recovery by "
            f"₹{optimized.uplift_amount} "
            f"(+{optimized.uplift_percent:.2f}%). "
            "This is an offline benchmark, not live merchant revenue."
        )

        tools = [
            "get_portfolio_summary",
        ]

        scope = "FROZEN OFFLINE EVALUATION"

    #
    # Optional grounded LLM explanation for non-financial-decision
    # queries.
    #
    provider = GroundedLLMProvider()

    generated = provider.explain(
        request.message,
        evidence,
    )

    return CopilotChatResponse(
        answer=generated or deterministic,
        facts=facts[:8],
        tools_used=tools,
        suggested_questions=SUGGESTED,
        ai_available=(
            provider.configured
            and generated is not None
        ),
        data_scope=scope,
    )
