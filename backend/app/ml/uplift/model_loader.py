"""Cached loading and validation for the persisted uplift artifact."""

from pathlib import Path
from typing import Any

import joblib

from app.decision.actions import RecoveryAction


PROJECT_ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "uplift_models.joblib"

CANONICAL_ACTIONS = [action.value for action in RecoveryAction]
CONTROL_ACTION = RecoveryAction.DO_NOTHING.value

_uplift_artifact = None


def _validate_uplift_artifact(artifact: Any) -> None:
    if not isinstance(artifact, dict):
        raise ValueError("Uplift model artifact must be a dictionary")

    if artifact.get("model_type") != "T-learner":
        raise ValueError("Uplift model artifact has an invalid model_type")

    if artifact.get("control_action") != CONTROL_ACTION:
        raise ValueError(
            f"Uplift model artifact must use {CONTROL_ACTION} as its control action"
        )

    actions = artifact.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Uplift model artifact is missing its action order")
    if len(actions) != len(CANONICAL_ACTIONS) or set(actions) != set(
        CANONICAL_ACTIONS
    ):
        raise ValueError(
            "Uplift model artifact actions do not match the canonical actions"
        )

    models = artifact.get("models")
    if not isinstance(models, dict):
        raise ValueError("Uplift model artifact is missing its model mapping")

    missing_models = [action for action in CANONICAL_ACTIONS if action not in models]
    if missing_models:
        raise ValueError(
            "Uplift model artifact is missing canonical models: "
            + ", ".join(missing_models)
        )

    invalid_models = [
        action
        for action in CANONICAL_ACTIONS
        if not callable(getattr(models[action], "predict_proba", None))
    ]
    if invalid_models:
        raise ValueError(
            "Uplift model artifact contains invalid models: "
            + ", ".join(invalid_models)
        )


def load_uplift_models() -> dict:
    """Load and cache the validated observational T-learner artifact."""
    global _uplift_artifact

    if _uplift_artifact is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Uplift models not found: {MODEL_PATH}")

        artifact = joblib.load(MODEL_PATH)
        _validate_uplift_artifact(artifact)
        _uplift_artifact = artifact

    return _uplift_artifact
