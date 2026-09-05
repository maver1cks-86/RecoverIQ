from pathlib import Path
import json
import sys

import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))


from app.ml.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
)


TRAIN_PATH = (
    ROOT
    / "data"
    / "processed"
    / "train.csv"
)

VALIDATION_PATH = (
    ROOT
    / "data"
    / "processed"
    / "validation.csv"
)

TEST_PATH = (
    ROOT
    / "data"
    / "processed"
    / "test.csv"
)


MODEL_DIR = (
    ROOT
    / "ml"
    / "models"
)

MODEL_PATH = (
    MODEL_DIR
    / "recovery_model.joblib"
)


METRICS_PATH = (
    MODEL_DIR
    / "recovery_model_metrics.json"
)


PREDICTIONS_PATH = (
    ROOT
    / "data"
    / "processed"
    / "recovery_model_test_predictions.csv"
)


def load_dataset(path):

    df = pd.read_csv(path)

    X = df[MODEL_FEATURES].copy()

    y = df[TARGET].astype(int)

    return df, X, y


def build_model():

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=True,
                ),
                CATEGORICAL_FEATURES,
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

    pipeline = Pipeline(
        steps=[
            (
                "preprocessor",
                preprocessor,
            ),
            (
                "classifier",
                classifier,
            ),
        ]
    )

    return pipeline


def evaluate_model(
    model,
    X,
    y,
):

    probabilities = (
        model.predict_proba(X)[:, 1]
    )

    predictions = (
        probabilities >= 0.5
    ).astype(int)

    metrics = {
        "roc_auc":
            float(
                roc_auc_score(
                    y,
                    probabilities,
                )
            ),

        "log_loss":
            float(
                log_loss(
                    y,
                    probabilities,
                )
            ),

        "brier_score":
            float(
                brier_score_loss(
                    y,
                    probabilities,
                )
            ),

        "accuracy":
            float(
                accuracy_score(
                    y,
                    predictions,
                )
            ),

        "precision":
            float(
                precision_score(
                    y,
                    predictions,
                    zero_division=0,
                )
            ),

        "recall":
            float(
                recall_score(
                    y,
                    predictions,
                    zero_division=0,
                )
            ),
    }

    return (
        metrics,
        probabilities,
    )


def print_metrics(
    title,
    metrics,
):

    print(
        f"\n{title}"
    )

    print(
        "-" * len(title)
    )

    for key, value in metrics.items():

        print(
            f"{key}: "
            f"{value:.4f}"
        )


def main():

    print(
        "Loading datasets..."
    )

    (
        train_df,
        X_train,
        y_train,
    ) = load_dataset(
        TRAIN_PATH
    )

    (
        validation_df,
        X_validation,
        y_validation,
    ) = load_dataset(
        VALIDATION_PATH
    )

    (
        test_df,
        X_test,
        y_test,
    ) = load_dataset(
        TEST_PATH
    )

    print(
        f"Train rows: "
        f"{len(train_df):,}"
    )

    print(
        f"Validation rows: "
        f"{len(validation_df):,}"
    )

    print(
        f"Test rows: "
        f"{len(test_df):,}"
    )

    print(
        "\nBuilding recovery model..."
    )

    model = build_model()

    print(
        "Training..."
    )

    model.fit(
        X_train,
        y_train,
    )

    validation_metrics, _ = (
        evaluate_model(
            model,
            X_validation,
            y_validation,
        )
    )

    print_metrics(
        "VALIDATION RESULTS",
        validation_metrics,
    )

    print(
        "\nEvaluating frozen test set..."
    )

    (
        test_metrics,
        test_probabilities,
    ) = evaluate_model(
        model,
        X_test,
        y_test,
    )

    print_metrics(
        "TEST RESULTS",
        test_metrics,
    )

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        MODEL_PATH,
    )

    metrics = {
        "model":
            "XGBoost recovery predictor",

        "train_rows":
            len(train_df),

        "validation_rows":
            len(validation_df),

        "test_rows":
            len(test_df),

        "features":
            MODEL_FEATURES,

        "validation":
            validation_metrics,

        "test":
            test_metrics,
    }

    with open(
        METRICS_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            metrics,
            f,
            indent=2,
        )

    predictions_df = pd.DataFrame(
        {
            "payment_id":
                test_df[
                    "payment_id"
                ].values,

            "failure_type":
                test_df[
                    "failure_type"
                ].values,

            "action_taken":
                test_df[
                    "action_taken"
                ].values,

            "actual_recovered":
                y_test.values,

            "predicted_recovery_probability":
                test_probabilities,
        }
    )

    predictions_df.to_csv(
        PREDICTIONS_PATH,
        index=False,
    )

    print(
        "\nModel saved to:"
    )

    print(
        MODEL_PATH
    )

    print(
        "\nMetrics saved to:"
    )

    print(
        METRICS_PATH
    )

    print(
        "\nPredictions saved to:"
    )

    print(
        PREDICTIONS_PATH
    )


if __name__ == "__main__":
    main()