"""Evaluate uplift estimates against deterministic synthetic ground truth."""

from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"

sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(BACKEND_ROOT))

from app.decision.actions import RecoveryAction
from app.ml.uplift.features import UPLIFT_FEATURES
from scripts.generate_dateset import calculate_recovery_probability


TEST_PATH = PROJECT_ROOT / "data" / "processed" / "test.csv"
MODEL_PATH = PROJECT_ROOT / "ml" / "models" / "uplift_models.joblib"
PREDICTIONS_PATH = (
    PROJECT_ROOT / "data" / "processed" / "uplift_test_predictions.csv"
)
EVALUATION_PATH = (
    PROJECT_ROOT / "data" / "processed" / "uplift_evaluation.csv"
)

EXPECTED_TEST_ROWS = 10_000
CONTROL_ACTION = RecoveryAction.DO_NOTHING.value
ACTIONS = [action.value for action in RecoveryAction]
EPSILON = 1e-9


def build_customer(row) -> dict:
    """Reconstruct the customer input expected by the frozen simulator."""
    return {
        "customer_tenure_days": int(row.customer_tenure_days),
        "successful_payments": int(row.successful_payments),
        "failed_payments": int(row.failed_payments),
        "previous_recoveries": int(row.previous_recoveries),
        "historical_recovery_rate": float(row.historical_recovery_rate),
        "avg_transaction_value": float(row.avg_transaction_value),
        "whatsapp_response_rate": float(row.whatsapp_response_rate),
        "email_response_rate": float(row.email_response_rate),
        "retry_success_rate": float(row.retry_success_rate),
        "payment_link_conversion_rate": float(
            row.payment_link_conversion_rate
        ),
        "price_sensitivity": float(row.price_sensitivity),
    }


def build_payment(row) -> dict:
    """Reconstruct the payment input expected by the frozen simulator."""
    return {
        "amount": float(row.amount),
        "payment_method": str(row.payment_method),
        "failure_type": str(row.failure_type),
        "failure_code": str(row.failure_code),
        "attempt_number": int(row.attempt_number),
        "hour": int(row.hour),
        "day_of_week": int(row.day_of_week),
    }


def load_inputs() -> tuple[pd.DataFrame, dict]:
    print("Loading frozen test set...")
    test_df = pd.read_csv(TEST_PATH)
    if len(test_df) != EXPECTED_TEST_ROWS:
        raise ValueError(
            f"Expected {EXPECTED_TEST_ROWS:,} test rows, found {len(test_df):,}"
        )

    required_columns = set(
        UPLIFT_FEATURES
        + ["payment_id", "amount", "failure_type", "payment_method"]
    )
    missing_columns = sorted(required_columns.difference(test_df.columns))
    if missing_columns:
        raise ValueError(
            "Test set is missing required columns: " + ", ".join(missing_columns)
        )
    print(f"Loaded {len(test_df):,} payments.")

    print("\nLoading uplift models...")
    artifact = joblib.load(MODEL_PATH)
    models = artifact.get("models", {})
    missing_actions = [action for action in ACTIONS if action not in models]
    if missing_actions:
        raise ValueError(
            "Uplift artifact is missing action models: "
            + ", ".join(missing_actions)
        )
    if len(models) != len(ACTIONS):
        raise ValueError(
            f"Expected exactly {len(ACTIONS)} action models, found {len(models)}"
        )
    if artifact.get("control_action") != CONTROL_ACTION:
        raise ValueError("Uplift artifact has an unexpected control action")
    if artifact.get("features") != UPLIFT_FEATURES:
        raise ValueError("Uplift artifact features do not match UPLIFT_FEATURES")
    print(f"Loaded {len(models)} action models.")
    return test_df, artifact


def predict_action_probabilities(
    test_df: pd.DataFrame,
    artifact: dict,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    print("\nRunning batched uplift inference...")
    X_test = test_df[UPLIFT_FEATURES]
    models = artifact["models"]
    control_probabilities = models[CONTROL_ACTION].predict_proba(X_test)[:, 1]
    probabilities = {}

    for action in ACTIONS:
        if action == CONTROL_ACTION:
            action_probabilities = control_probabilities.copy()
        else:
            action_probabilities = models[action].predict_proba(X_test)[:, 1]
        probabilities[action] = np.asarray(action_probabilities, dtype=float)
        print(f"Predicted action: {action}")

    all_probabilities = np.concatenate(list(probabilities.values()))
    if not np.isfinite(all_probabilities).all():
        raise ValueError("Predicted probabilities contain NaN or infinite values")
    if ((all_probabilities < 0.0) | (all_probabilities > 1.0)).any():
        raise ValueError("Predicted probabilities fall outside [0, 1]")
    return probabilities, np.asarray(control_probabilities, dtype=float)


def calculate_ground_truth(
    test_df: pd.DataFrame,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    print("\nComputing simulator ground truth...")
    true_probabilities = {
        action: np.empty(len(test_df), dtype=float)
        for action in ACTIONS
    }

    for index, row in enumerate(test_df.itertuples(index=False), start=1):
        customer = build_customer(row)
        payment = build_payment(row)
        control_probability = calculate_recovery_probability(
            customer=customer,
            payment=payment,
            action=CONTROL_ACTION,
            add_noise=False,
        )

        for action in ACTIONS:
            probability = (
                control_probability
                if action == CONTROL_ACTION
                else calculate_recovery_probability(
                    customer=customer,
                    payment=payment,
                    action=action,
                    add_noise=False,
                )
            )
            true_probabilities[action][index - 1] = probability

        if index % 1_000 == 0:
            print(f"Processed {index:,}/{len(test_df):,}")

    all_probabilities = np.concatenate(list(true_probabilities.values()))
    if not np.isfinite(all_probabilities).all():
        raise ValueError("Simulator probabilities contain NaN or infinite values")
    if ((all_probabilities < 0.0) | (all_probabilities > 1.0)).any():
        raise ValueError("Simulator probabilities fall outside [0, 1]")
    return true_probabilities, true_probabilities[CONTROL_ACTION].copy()


def build_detailed_predictions(
    test_df: pd.DataFrame,
    predicted_probabilities: dict[str, np.ndarray],
    predicted_control: np.ndarray,
    true_probabilities: dict[str, np.ndarray],
    true_control: np.ndarray,
) -> pd.DataFrame:
    frames = []
    for action in ACTIONS:
        predicted_uplift = (
            np.zeros(len(test_df), dtype=float)
            if action == CONTROL_ACTION
            else predicted_probabilities[action] - predicted_control
        )
        true_uplift = (
            np.zeros(len(test_df), dtype=float)
            if action == CONTROL_ACTION
            else true_probabilities[action] - true_control
        )
        frames.append(
            pd.DataFrame(
                {
                    "payment_id": test_df["payment_id"].to_numpy(),
                    "action": action,
                    "amount": test_df["amount"].to_numpy(),
                    "failure_type": test_df["failure_type"].to_numpy(),
                    "payment_method": test_df["payment_method"].to_numpy(),
                    "attempt_number": test_df["attempt_number"].to_numpy(),
                    "predicted_treatment_probability": predicted_probabilities[action],
                    "predicted_control_probability": predicted_control,
                    "predicted_uplift": predicted_uplift,
                    "true_treatment_probability": true_probabilities[action],
                    "true_control_probability": true_control,
                    "true_uplift": true_uplift,
                    "uplift_error": predicted_uplift - true_uplift,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def safe_correlation(
    left: pd.Series,
    right: pd.Series,
    method: str,
) -> float | None:
    if left.std(ddof=0) <= EPSILON or right.std(ddof=0) <= EPSILON:
        return None
    correlation = left.corr(right, method=method)
    return float(correlation) if pd.notna(correlation) else None


def sign_labels(values: pd.Series) -> np.ndarray:
    array = values.to_numpy(dtype=float)
    return np.where(array > EPSILON, 1, np.where(array < -EPSILON, -1, 0))


def calculate_metrics(action_df: pd.DataFrame) -> dict:
    errors = action_df["uplift_error"]
    predicted = action_df["predicted_uplift"]
    truth = action_df["true_uplift"]
    top_count = max(1, int(np.ceil(len(action_df) * 0.10)))
    top_decile = action_df.nlargest(top_count, "predicted_uplift")
    overall_mean_true = float(truth.mean())
    top_mean_true = float(top_decile["true_uplift"].mean())

    return {
        "test_samples": len(action_df),
        "mae": float(errors.abs().mean()),
        "rmse": float(np.sqrt(np.mean(np.square(errors)))),
        "pearson_correlation": safe_correlation(predicted, truth, "pearson"),
        "spearman_correlation": safe_correlation(predicted, truth, "spearman"),
        "sign_accuracy": float(
            np.mean(sign_labels(predicted) == sign_labels(truth))
        ),
        "mean_predicted_uplift": float(predicted.mean()),
        "mean_true_uplift": overall_mean_true,
        "predicted_uplift_std": float(predicted.std(ddof=0)),
        "true_uplift_std": float(truth.std(ddof=0)),
        "top_decile_mean_true_uplift": top_mean_true,
        "overall_mean_true_uplift": overall_mean_true,
        "top_decile_gain": top_mean_true - overall_mean_true,
    }


def evaluate_predictions(
    detailed_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    rows = []
    for action in ACTIONS:
        action_df = detailed_df.loc[detailed_df["action"] == action]
        rows.append({"action": action, **calculate_metrics(action_df)})

    evaluation_df = pd.DataFrame(rows)
    non_control = detailed_df.loc[detailed_df["action"] != CONTROL_ACTION]
    overall = calculate_metrics(non_control)
    return evaluation_df, overall


def run_sanity_checks(
    test_df: pd.DataFrame,
    detailed_df: pd.DataFrame,
    evaluation_df: pd.DataFrame,
) -> None:
    expected_detail_rows = len(test_df) * len(ACTIONS)
    if len(detailed_df) != expected_detail_rows:
        raise AssertionError(
            f"Expected {expected_detail_rows:,} detail rows, found {len(detailed_df):,}"
        )
    action_counts = detailed_df.groupby("payment_id")["action"].nunique()
    if not (action_counts == len(ACTIONS)).all():
        raise AssertionError("Every payment must have exactly nine unique actions")
    if len(action_counts) != len(test_df):
        raise AssertionError("Detailed output does not contain every test payment")
    if detailed_df.isna().any().any():
        raise AssertionError("Detailed output contains missing values")

    control = detailed_df.loc[detailed_df["action"] == CONTROL_ACTION]
    if not np.allclose(control["predicted_uplift"], 0.0, atol=EPSILON):
        raise AssertionError("DO_NOTHING predicted uplift is not zero")
    if not np.allclose(control["true_uplift"], 0.0, atol=EPSILON):
        raise AssertionError("DO_NOTHING true uplift is not zero")
    if set(evaluation_df["action"]) != set(ACTIONS):
        raise AssertionError("Evaluation summary does not contain all actions")
    print("\nAll uplift evaluation sanity checks passed.")


def print_results(evaluation_df: pd.DataFrame, overall: dict) -> None:
    print("\nUPLIFT MODEL EVALUATION")
    print("-" * 112)
    print(
        f"{'ACTION':20s}{'MAE':>10s}{'RMSE':>10s}{'PEARSON':>12s}"
        f"{'SPEARMAN':>12s}{'SIGN ACC':>12s}{'TOP-10 GAIN':>14s}"
    )
    for row in evaluation_df.itertuples(index=False):
        pearson = "n/a" if pd.isna(row.pearson_correlation) else f"{row.pearson_correlation:.4f}"
        spearman = "n/a" if pd.isna(row.spearman_correlation) else f"{row.spearman_correlation:.4f}"
        print(
            f"{row.action:20s}{row.mae:10.4f}{row.rmse:10.4f}"
            f"{pearson:>12s}{spearman:>12s}{row.sign_accuracy:12.4f}"
            f"{row.top_decile_gain:14.4f}"
        )

    print("\nOVERALL (8 NON-CONTROL ACTIONS)")
    for key in ("mae", "rmse", "pearson_correlation", "spearman_correlation", "sign_accuracy"):
        print(f"  {key}: {overall[key]:.6f}")


def main() -> None:
    test_df, artifact = load_inputs()
    predicted, predicted_control = predict_action_probabilities(test_df, artifact)
    truth, true_control = calculate_ground_truth(test_df)
    detailed_df = build_detailed_predictions(
        test_df,
        predicted,
        predicted_control,
        truth,
        true_control,
    )
    evaluation_df, overall = evaluate_predictions(detailed_df)
    run_sanity_checks(test_df, detailed_df, evaluation_df)
    print_results(evaluation_df, overall)

    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    detailed_df.to_csv(PREDICTIONS_PATH, index=False)
    evaluation_df.to_csv(EVALUATION_PATH, index=False)
    print("\nSaved:")
    print(PREDICTIONS_PATH)
    print(EVALUATION_PATH)
    print(
        "\nThe synthetic simulator provides known counterfactual recovery "
        "probabilities, allowing estimated treatment effects to be compared "
        "directly against simulator ground truth."
    )


if __name__ == "__main__":
    main()
