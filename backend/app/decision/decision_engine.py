from dataclasses import dataclass

from app.decision.action_evaluator import (
    ActionEvaluator,
    ActionPrediction,
)

from app.decision.economic_value import (
    EconomicValue,
    calculate_economic_value,
)

from app.ml.uplift.uplift_predictor import (
    UpliftPrediction,
    UpliftPredictor,
)

from app.policies.engine import (
    PolicyConfig,
    PolicyDecision,
    PolicyEngine,
)


@dataclass(frozen=True)
class RecoveryDecision:
    recommended_action: str
    recovery_probability: float
    expected_net_value: float
    incremental_value: float

    ranked_actions: list[EconomicValue]

    policy_decisions: list[PolicyDecision]


class DecisionEngine:

    def __init__(self):

        self.action_evaluator = (
            ActionEvaluator()
        )

        self.uplift_predictor = (
            UpliftPredictor()
        )

        self.policy_engine = (
            PolicyEngine()
        )

    def evaluate(
        self,
        context: dict,
        policy: PolicyConfig | None = None,
    ) -> RecoveryDecision:
        """
        Evaluate one payment normally.

        Flow:

        1. Predict absolute recovery probability
           for each candidate action.

        2. Estimate uplift relative to DO_NOTHING.

        3. Calculate predictive expected value and
           uplift-aware incremental value.

        4. Apply merchant policy constraints.

        5. Rank eligible actions by incremental value.

        This method is intended for:
        - API calls
        - individual payment decisions
        - normal non-batch evaluation
        """

        predictions = (
            self.action_evaluator
            .evaluate(
                context
            )
        )

        uplift_predictions = (
            self.uplift_predictor
            .predict_all_uplifts(
                context
            )
        )

        return self.evaluate_from_predictions(
            context=context,
            predictions=predictions,
            uplift_predictions=(
                uplift_predictions
            ),
            policy=policy,
        )

    def evaluate_from_predictions(
        self,
        context: dict,
        predictions: list[ActionPrediction],
        policy: PolicyConfig | None = None,
        uplift_predictions: (
            list[UpliftPrediction] | None
        ) = None,
    ) -> RecoveryDecision:
        """
        Evaluate a payment when predictive recovery
        probabilities have already been computed.

        Optionally accepts precomputed uplift predictions.

        This keeps the method usable for future batch
        experiments where both recovery probabilities
        and uplift estimates can be computed in batches.

        If uplift_predictions is not supplied, uplift
        is calculated normally for this context.
        """

        if policy is None:
            policy = PolicyConfig()

        amount = float(
            context["amount"]
        )

        # -------------------------------------------------
        # STEP 1
        # Obtain uplift estimates.
        # -------------------------------------------------

        if uplift_predictions is None:

            uplift_predictions = (
                self.uplift_predictor
                .predict_all_uplifts(
                    context
                )
            )

        uplift_by_action = {
            item.action: item
            for item
            in uplift_predictions
        }

        prediction_actions = {
            item.action
            for item
            in predictions
        }

        uplift_actions = set(
            uplift_by_action.keys()
        )

        if prediction_actions != uplift_actions:
            raise ValueError(
                "Recovery predictions and uplift "
                "predictions contain different "
                "action sets."
            )

        # -------------------------------------------------
        # STEP 2
        # Calculate economic value for every action.
        #
        # recovery_probability:
        #     used for predictive expected value
        #
        # estimated_uplift:
        #     used for incremental economic value
        # -------------------------------------------------

        economic_values = []

        for prediction in predictions:

            uplift_prediction = (
                uplift_by_action[
                    prediction.action
                ]
            )

            value = (
                calculate_economic_value(
                    action=(
                        prediction.action
                    ),

                    recovery_probability=(
                        prediction
                        .recovery_probability
                    ),

                    estimated_uplift=(
                        uplift_prediction
                        .uplift
                    ),

                    amount=amount,
                )
            )

            economic_values.append(
                value
            )

        # -------------------------------------------------
        # STEP 3
        # Verify DO_NOTHING exists.
        #
        # DO_NOTHING is the control and guarantees a
        # zero-incremental-value feasible alternative.
        # -------------------------------------------------

        do_nothing = next(
            (
                item
                for item
                in economic_values
                if item.action
                == "DO_NOTHING"
            ),
            None,
        )

        if do_nothing is None:
            raise ValueError(
                "DO_NOTHING action is required."
            )

        if do_nothing.estimated_uplift != 0.0:
            raise ValueError(
                "DO_NOTHING estimated uplift "
                "must be exactly zero."
            )

        if do_nothing.incremental_value != 0.0:
            raise ValueError(
                "DO_NOTHING incremental value "
                "must be exactly zero."
            )

        # -------------------------------------------------
        # STEP 4
        # Apply merchant policy.
        # -------------------------------------------------

        action_names = [
            item.action
            for item
            in economic_values
        ]

        (
            allowed_actions,
            policy_decisions,
        ) = self.policy_engine.filter_actions(
            actions=action_names,
            context=context,
            policy=policy,
        )

        allowed_action_set = set(
            allowed_actions
        )

        eligible_values = [
            item
            for item
            in economic_values
            if item.action
            in allowed_action_set
        ]

        # -------------------------------------------------
        # DO_NOTHING should guarantee feasibility.
        # -------------------------------------------------

        if not eligible_values:
            raise ValueError(
                "Policy removed all recovery actions."
            )

        # -------------------------------------------------
        # STEP 5
        # Rank eligible actions by UPLIFT-AWARE
        # incremental economic value.
        #
        # This replaces the old Phase 17 ranking by
        # absolute expected_net_value.
        #
        # Because DO_NOTHING has incremental value 0,
        # economically harmful interventions naturally
        # rank below doing nothing.
        # -------------------------------------------------

        ranked_actions = sorted(
            eligible_values,
            key=lambda item:
                item.incremental_value,
            reverse=True,
        )

        best = ranked_actions[0]

        # -------------------------------------------------
        # STEP 6
        # Return decision + policy audit trail.
        #
        # We retain predictive recovery_probability and
        # expected_net_value for explanation/dashboarding.
        #
        # incremental_value now represents estimated
        # uplift-aware economic contribution.
        # -------------------------------------------------

        return RecoveryDecision(
            recommended_action=(
                best.action
            ),

            recovery_probability=(
                best.recovery_probability
            ),

            expected_net_value=(
                best.expected_net_value
            ),

            incremental_value=(
                best.incremental_value
            ),

            ranked_actions=(
                ranked_actions
            ),

            policy_decisions=(
                policy_decisions
            ),
        )