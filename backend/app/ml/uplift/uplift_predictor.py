"""Runtime inference for observational T-learner uplift estimates."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.ml.uplift.features import UPLIFT_FEATURES
from app.ml.uplift.model_loader import load_uplift_models


@dataclass(frozen=True)
class UpliftPrediction:
    action: str
    treatment_probability: float
    control_probability: float
    uplift: float


class UpliftPredictor:
    """Estimate action uplift relative to the persisted control model."""

    def __init__(self) -> None:
        self.artifact = load_uplift_models()
        self.control_action = self.artifact["control_action"]
        self.actions = list(self.artifact["actions"])
        self.models = self.artifact["models"]

    def _validate_action(self, action: str) -> None:
        if action not in self.models:
            raise ValueError(
                f"Unknown uplift action: {action!r}. "
                f"Expected one of: {', '.join(self.actions)}"
            )

    def _build_model_input(
        self,
        contexts: list[dict[str, Any]],
    ) -> pd.DataFrame:
        rows = []

        for index, context in enumerate(contexts):
            missing_features = [
                feature for feature in UPLIFT_FEATURES if feature not in context
            ]
            if missing_features:
                raise ValueError(
                    f"Missing uplift model features for context {index}: "
                    + ", ".join(missing_features)
                )

            rows.append(
                {feature: context[feature] for feature in UPLIFT_FEATURES}
            )

        return pd.DataFrame(rows, columns=UPLIFT_FEATURES)

    @staticmethod
    def _validated_probabilities(
        probabilities: Any,
        action: str,
        expected_rows: int,
    ) -> np.ndarray:
        values = np.asarray(probabilities, dtype=float)
        if values.shape != (expected_rows,):
            raise ValueError(
                f"Uplift model {action} returned an unexpected probability shape: "
                f"{values.shape}"
            )
        if not np.isfinite(values).all():
            raise ValueError(f"Uplift model {action} returned non-finite probabilities")
        if ((values < 0.0) | (values > 1.0)).any():
            raise ValueError(
                f"Uplift model {action} returned probabilities outside [0, 1]"
            )
        return values

    def _predict_probabilities(
        self,
        model_input: pd.DataFrame,
        action: str,
    ) -> np.ndarray:
        probabilities = self.models[action].predict_proba(model_input)[:, 1]
        return self._validated_probabilities(
            probabilities,
            action,
            len(model_input),
        )

    def predict_uplift(
        self,
        context: dict[str, Any],
        action: str,
    ) -> UpliftPrediction:
        """Estimate uplift for one payment-action pair."""
        self._validate_action(action)
        model_input = self._build_model_input([context])
        control_probability = float(
            self._predict_probabilities(model_input, self.control_action)[0]
        )

        if action == self.control_action:
            treatment_probability = control_probability
            uplift = 0.0
        else:
            treatment_probability = float(
                self._predict_probabilities(model_input, action)[0]
            )
            uplift = treatment_probability - control_probability

        return UpliftPrediction(
            action=action,
            treatment_probability=treatment_probability,
            control_probability=control_probability,
            uplift=uplift,
        )

    def predict_all_uplifts(
        self,
        context: dict[str, Any],
    ) -> list[UpliftPrediction]:
        """Estimate all canonical action uplifts for one payment."""
        return self.predict_all_uplifts_batch([context])[0]

    def predict_all_uplifts_batch(
        self,
        contexts: list[dict[str, Any]],
    ) -> list[list[UpliftPrediction]]:
        """
        Estimate all action uplifts for a batch using one call per model.

        Results preserve context order and the action order stored in the
        validated artifact.
        """
        if not contexts:
            return []

        model_input = self._build_model_input(contexts)
        control_probabilities = self._predict_probabilities(
            model_input,
            self.control_action,
        )
        probabilities_by_action = {self.control_action: control_probabilities}

        for action in self.actions:
            if action != self.control_action:
                probabilities_by_action[action] = self._predict_probabilities(
                    model_input,
                    action,
                )

        results = []
        for context_index in range(len(contexts)):
            control_probability = float(control_probabilities[context_index])
            context_results = []

            for action in self.actions:
                treatment_probability = float(
                    probabilities_by_action[action][context_index]
                )
                uplift = (
                    0.0
                    if action == self.control_action
                    else treatment_probability - control_probability
                )
                context_results.append(
                    UpliftPrediction(
                        action=action,
                        treatment_probability=treatment_probability,
                        control_probability=control_probability,
                        uplift=uplift,
                    )
                )

            results.append(context_results)

        return results
