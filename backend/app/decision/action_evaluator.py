from dataclasses import dataclass

from app.decision.candidate_actions import (
    get_candidate_actions,
)

from app.ml.recovery_predictor import (
    RecoveryPredictor,
)


@dataclass(frozen=True)
class ActionPrediction:
    action: str
    recovery_probability: float


class ActionEvaluator:

    def __init__(self):
        self.predictor = RecoveryPredictor()

    def evaluate(
        self,
        context: dict,
    ) -> list[ActionPrediction]:
        """
        Evaluate one payment across all
        candidate recovery actions.
        """

        actions = get_candidate_actions(
            context
        )

        predictions = []

        for action in actions:

            probability = (
                self.predictor
                .predict_probability(
                    context,
                    action,
                )
            )

            predictions.append(
                ActionPrediction(
                    action=action,
                    recovery_probability=float(
                        probability
                    ),
                )
            )

        return predictions

    def evaluate_batch(
        self,
        contexts: list[dict],
    ) -> list[list[ActionPrediction]]:
        """
        Evaluate many payments across all
        candidate recovery actions using one
        batched model prediction.

        Returns one list of ActionPrediction
        objects for every context.
        """

        if not contexts:
            return []

        actions = get_candidate_actions(
            contexts[0]
        )

        probabilities = (
            self.predictor
            .predict_probabilities_batch(
                contexts=contexts,
                actions=actions,
            )
        )

        results = []

        for context_probabilities in probabilities:

            predictions = []

            for action, probability in zip(
                actions,
                context_probabilities,
            ):

                predictions.append(
                    ActionPrediction(
                        action=action,
                        recovery_probability=float(
                            probability
                        ),
                    )
                )

            results.append(
                predictions
            )

        return results