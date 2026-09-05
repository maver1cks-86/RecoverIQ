from fastapi import APIRouter, HTTPException

from app.decision.decision_engine import (
    DecisionEngine,
)

from app.policies.engine import (
    PolicyConfig,
)

from app.schemas.recovery import (
    RecoveryEvaluationRequest,
    RecoveryEvaluationResponse,
    RankedActionResponse,
    PolicyDecisionResponse,
)


router = APIRouter(
    prefix="/recovery",
    tags=["recovery"],
)


decision_engine = DecisionEngine()


@router.post(
    "/evaluate",
    response_model=RecoveryEvaluationResponse,
)
def evaluate_recovery(
    request: RecoveryEvaluationRequest,
) -> RecoveryEvaluationResponse:

    try:
        context = (
            request.context.model_dump()
        )

        # -----------------------------------------
        # Build policy config
        # -----------------------------------------

        if request.policy is None:

            policy = PolicyConfig()

        else:

            policy_data = (
                request.policy.model_dump()
            )

            allowed_actions = (
                policy_data.pop(
                    "allowed_actions"
                )
            )

            if allowed_actions is None:

                policy = PolicyConfig(
                    **policy_data
                )

            else:

                policy = PolicyConfig(
                    allowed_actions=set(
                        allowed_actions
                    ),
                    **policy_data,
                )

        # -----------------------------------------
        # Run complete decision pipeline
        # -----------------------------------------

        decision = (
            decision_engine.evaluate(
                context=context,
                policy=policy,
            )
        )

        # -----------------------------------------
        # Convert decision objects to API response
        # -----------------------------------------

        ranked_actions = [
            RankedActionResponse(
                action=item.action,

                recovery_probability=(
                    item.recovery_probability
                ),

                intervention_cost=(
                    item.intervention_cost
                ),

                incentive_cost=(
                    item.incentive_cost
                ),

                expected_gross_value=(
                    item.expected_gross_value
                ),

                expected_net_value=(
                    item.expected_net_value
                ),

                incremental_value=(
                    item.incremental_value
                ),
            )
            for item
            in decision.ranked_actions
        ]

        policy_decisions = [
            PolicyDecisionResponse(
                action=item.action,
                allowed=item.allowed,
                reason=item.reason,
                requires_approval=item.requires_approval,
            )
            for item
            in decision.policy_decisions
        ]

        return RecoveryEvaluationResponse(
            recommended_action=(
                decision.recommended_action
            ),

            recovery_probability=(
                decision.recovery_probability
            ),

            expected_net_value=(
                decision.expected_net_value
            ),

            incremental_value=(
                decision.incremental_value
            ),

            ranked_actions=(
                ranked_actions
            ),

            policy_decisions=(
                policy_decisions
            ),
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Recovery evaluation failed: "
                f"{str(exc)}"
            ),
        ) from exc
