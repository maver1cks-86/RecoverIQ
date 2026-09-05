from typing import Any

import pandas as pd

from app.ml.features import MODEL_FEATURES
from app.ml.model_loader import load_recovery_model


class RecoveryPredictor:

    def __init__(self):

        self.model = (
            load_recovery_model()
        )

    def predict_probability(
        self,
        context: dict[str, Any],
        action: str,
    ) -> float:
        """
        Predict recovery probability for one
        payment-action pair.
        """

        row = context.copy()

        row["action_taken"] = action

        missing_features = [
            feature
            for feature in MODEL_FEATURES
            if feature not in row
        ]

        if missing_features:
            raise ValueError(
                "Missing recovery model features: "
                + ", ".join(missing_features)
            )

        model_input = pd.DataFrame(
            [
                {
                    feature: row[feature]
                    for feature in MODEL_FEATURES
                }
            ],
            columns=MODEL_FEATURES,
        )

        probability = (
            self.model
            .predict_proba(
                model_input
            )[0][1]
        )

        return float(
            probability
        )

    def predict_probabilities_batch(
        self,
        contexts: list[dict[str, Any]],
        actions: list[str],
    ) -> list[list[float]]:
        """
        Predict every candidate action for many
        payment contexts using one model call.

        Example:

        10,000 contexts
        x 9 actions
        =
        90,000 rows passed to predict_proba()
        in one batch.

        Returns:

        [
            [p_action_1, p_action_2, ...],
            [p_action_1, p_action_2, ...],
            ...
        ]

        Each outer row corresponds to one context.
        Each inner value corresponds to actions
        in the same order as the supplied actions list.
        """

        if not contexts:
            return []

        if not actions:
            return [
                []
                for _ in contexts
            ]

        rows = []

        # -----------------------------------------
        # Build one large payment-action matrix.
        # -----------------------------------------

        for context in contexts:

            missing_features = [
                feature
                for feature in MODEL_FEATURES
                if (
                    feature != "action_taken"
                    and feature not in context
                )
            ]

            if missing_features:
                raise ValueError(
                    "Missing recovery model features: "
                    + ", ".join(
                        missing_features
                    )
                )

            for action in actions:

                row = context.copy()

                row["action_taken"] = (
                    action
                )

                rows.append(
                    {
                        feature:
                            row[feature]
                        for feature
                        in MODEL_FEATURES
                    }
                )

        # -----------------------------------------
        # One DataFrame for all contexts/actions.
        # -----------------------------------------

        batch_df = pd.DataFrame(
            rows,
            columns=MODEL_FEATURES,
        )

        # -----------------------------------------
        # ONE model inference call.
        # -----------------------------------------

        probabilities = (
            self.model
            .predict_proba(
                batch_df
            )[:, 1]
        )

        # -----------------------------------------
        # Reshape flat prediction array back into:
        #
        # payment -> actions -> probability
        # -----------------------------------------

        action_count = len(
            actions
        )

        result = []

        for index in range(
            len(contexts)
        ):

            start = (
                index
                * action_count
            )

            end = (
                start
                + action_count
            )

            context_probabilities = (
                probabilities[
                    start:end
                ]
                .astype(float)
                .tolist()
            )

            result.append(
                context_probabilities
            )

        return result