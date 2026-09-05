from pathlib import Path

import joblib


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

MODEL_PATH = (
    PROJECT_ROOT
    / "ml"
    / "models"
    / "recovery_model.joblib"
)


_recovery_model = None


def load_recovery_model():

    global _recovery_model

    if _recovery_model is None:

        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Recovery model not found: {MODEL_PATH}"
            )

        _recovery_model = joblib.load(
            MODEL_PATH
        )

    return _recovery_model