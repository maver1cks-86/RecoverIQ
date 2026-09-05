"""Train observational action-specific recovery models for a T-learner."""

import json
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))

from app.decision.actions import RecoveryAction
from app.ml.uplift.features import (
    UPLIFT_CATEGORICAL_FEATURES,
    UPLIFT_FEATURES,
    UPLIFT_NUMERIC_FEATURES,
)


TRAIN_PATH = ROOT / "data" / "processed" / "train.csv"
VALIDATION_PATH = ROOT / "data" / "processed" / "validation.csv"
MODEL_DIR = ROOT / "ml" / "models"
MODEL_PATH = MODEL_DIR / "uplift_models.joblib"
METRICS_PATH = MODEL_DIR / "uplift_model_metrics.json"

TARGET = "recovered"
TREATMENT = "action_taken"
CONTROL_ACTION = RecoveryAction.DO_NOTHING.value
ACTIONS = [action.value for action in RecoveryAction]


def load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required_columns = set(UPLIFT_FEATURES + [TARGET, TREATMENT])
    missing_columns = sorted(required_columns.difference(df.columns))

    if missing_columns:
        raise ValueError(
            f"Dataset {path} is missing required columns: "
            + ", ".join(missing_columns)
        )

    return df


def build_model() -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", "passthrough", UPLIFT_NUMERIC_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True),
                UPLIFT_CATEGORICAL_FEATURES,
            ),
        ]
    )

    classifier = XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        min_child_weight=3,
        reg_alpha=0.05,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def validate_training_actions(train_df: pd.DataFrame) -> None:
    observed_actions = set(train_df[TREATMENT].dropna().unique())
    missing_actions = [action for action in ACTIONS if action not in observed_actions]

    if missing_actions:
        raise ValueError(
            "Expected actions missing from training data: "
            + ", ".join(missing_actions)
        )

    for action in ACTIONS:
        action_target = train_df.loc[train_df[TREATMENT] == action, TARGET]
        if len(action_target) < 2:
            raise ValueError(
                f"Action {action} has insufficient training rows: "
                f"{len(action_target)}"
            )
        if action_target.nunique() < 2:
            raise ValueError(
                f"Action {action} training rows contain only one target class"
            )


def evaluate_model(
    model: Pipeline,
    validation_df: pd.DataFrame,
) -> dict[str, float | int | None]:
    y_validation = validation_df[TARGET].astype(int)
    probabilities = model.predict_proba(
        validation_df[UPLIFT_FEATURES]
    )[:, 1]

    roc_auc = None
    if y_validation.nunique() == 2:
        roc_auc = float(roc_auc_score(y_validation, probabilities))

    return {
        "roc_auc": roc_auc,
        "log_loss": float(
            log_loss(y_validation, probabilities, labels=[0, 1])
        ),
        "brier_score": float(
            brier_score_loss(y_validation, probabilities)
        ),
    }


def main() -> None:
    print("Loading train/validation data...")
    train_df = load_dataset(TRAIN_PATH)
    validation_df = load_dataset(VALIDATION_PATH)
    validate_training_actions(train_df)

    print(f"Train rows: {len(train_df):,}")
    print(f"Validation rows: {len(validation_df):,}")
    print("\nTraining uplift T-learner models...")

    models = {}
    per_action_metrics = {}

    for action in ACTIONS:
        action_train = train_df.loc[train_df[TREATMENT] == action].copy()
        action_validation = validation_df.loc[
            validation_df[TREATMENT] == action
        ].copy()

        if action_validation.empty:
            raise ValueError(
                f"Expected action {action} is missing from validation data"
            )

        X_train = action_train[UPLIFT_FEATURES]
        y_train = action_train[TARGET].astype(int)
        model = build_model()

        print(f"\nTraining action: {action}")
        print(f"  train rows: {len(action_train):,}")
        print(f"  validation rows: {len(action_validation):,}")

        model.fit(X_train, y_train)
        validation_metrics = evaluate_model(model, action_validation)

        action_metrics = {
            "training_samples": len(action_train),
            "validation_samples": len(action_validation),
            "training_positive_rate": float(y_train.mean()),
            "validation_positive_rate": float(
                action_validation[TARGET].astype(int).mean()
            ),
            **validation_metrics,
        }
        models[action] = model
        per_action_metrics[action] = action_metrics

        roc_auc_display = (
            f"{validation_metrics['roc_auc']:.4f}"
            if validation_metrics["roc_auc"] is not None
            else "n/a (single validation class)"
        )
        print(f"  validation ROC AUC: {roc_auc_display}")
        print(f"  validation log loss: {validation_metrics['log_loss']:.4f}")
        print(f"  validation Brier score: {validation_metrics['brier_score']:.4f}")

    artifact = {
        "model_type": "T-learner",
        "control_action": CONTROL_ACTION,
        "actions": ACTIONS,
        "features": UPLIFT_FEATURES,
        "models": models,
    }
    metrics = {
        "model_type": "T-learner",
        "control_action": CONTROL_ACTION,
        "features": UPLIFT_FEATURES,
        "per_action_metrics": per_action_metrics,
        "total_training_rows": len(train_df),
        "total_validation_rows": len(validation_df),
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    with METRICS_PATH.open("w", encoding="utf-8") as metrics_file:
        json.dump(metrics, metrics_file, indent=2)

    print(f"\nSaved uplift models to: {MODEL_PATH}")
    print(f"Saved uplift metrics to: {METRICS_PATH}")


if __name__ == "__main__":
    main()
