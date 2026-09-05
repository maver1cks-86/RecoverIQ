"""Standalone smoke checks for the Phase 18D UpliftPredictor."""

from collections import Counter
import math
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.decision.actions import RecoveryAction
from app.ml.uplift.model_loader import load_uplift_models
from app.ml.uplift.uplift_predictor import UpliftPredictor


ACTIONS = [action.value for action in RecoveryAction]

CONTEXTS = [
    {
        "amount": 1499.0,
        "attempt_number": 1,
        "hour": 10,
        "day_of_week": 2,
        "customer_tenure_days": 420,
        "successful_payments": 12,
        "failed_payments": 2,
        "previous_recoveries": 1,
        "historical_recovery_rate": 0.72,
        "avg_transaction_value": 1800.0,
        "whatsapp_response_rate": 0.68,
        "email_response_rate": 0.31,
        "retry_success_rate": 0.57,
        "payment_link_conversion_rate": 0.44,
        "price_sensitivity": 0.25,
        "payment_method": "UPI",
        "failure_code": "BANK_TIMEOUT",
        "failure_type": "TEMPORARY_BANK_FAILURE",
    },
    {
        "amount": 8250.0,
        "attempt_number": 3,
        "hour": 21,
        "day_of_week": 5,
        "customer_tenure_days": 90,
        "successful_payments": 2,
        "failed_payments": 5,
        "previous_recoveries": 0,
        "historical_recovery_rate": 0.18,
        "avg_transaction_value": 5100.0,
        "whatsapp_response_rate": 0.22,
        "email_response_rate": 0.48,
        "retry_success_rate": 0.12,
        "payment_link_conversion_rate": 0.63,
        "price_sensitivity": 0.82,
        "payment_method": "CARD",
        "failure_code": "INSUFFICIENT_FUNDS",
        "failure_type": "INSUFFICIENT_FUNDS",
    },
    {
        "amount": 650.0,
        "attempt_number": 2,
        "hour": 14,
        "day_of_week": 0,
        "customer_tenure_days": 760,
        "successful_payments": 28,
        "failed_payments": 4,
        "previous_recoveries": 3,
        "historical_recovery_rate": 0.81,
        "avg_transaction_value": 920.0,
        "whatsapp_response_rate": 0.74,
        "email_response_rate": 0.59,
        "retry_success_rate": 0.66,
        "payment_link_conversion_rate": 0.51,
        "price_sensitivity": 0.47,
        "payment_method": "NETBANKING",
        "failure_code": "PAYMENT_METHOD_UNAVAILABLE",
        "failure_type": "PAYMENT_METHOD_ISSUE",
    },
]


class CountingModel:
    def __init__(self, model, action: str, calls: Counter) -> None:
        self.model = model
        self.action = action
        self.calls = calls

    def predict_proba(self, model_input):
        self.calls[self.action] += 1
        return self.model.predict_proba(model_input)


def assert_prediction_is_valid(prediction) -> None:
    assert 0.0 <= prediction.treatment_probability <= 1.0
    assert 0.0 <= prediction.control_probability <= 1.0
    assert math.isfinite(prediction.uplift)
    if prediction.action == RecoveryAction.DO_NOTHING.value:
        assert prediction.treatment_probability == prediction.control_probability
        assert prediction.uplift == 0.0


def main() -> None:
    print("Loading uplift artifact...")
    artifact = load_uplift_models()
    assert artifact["actions"] == ACTIONS
    assert set(artifact["models"]) == set(ACTIONS)
    print("Artifact load check passed.")

    predictor = UpliftPredictor()

    print("Checking single-action prediction...")
    single = predictor.predict_uplift(CONTEXTS[0], RecoveryAction.RETRY_LATER.value)
    assert single.action == RecoveryAction.RETRY_LATER.value
    assert_prediction_is_valid(single)

    print("Checking all-action prediction...")
    all_predictions = predictor.predict_all_uplifts(CONTEXTS[0])
    assert [prediction.action for prediction in all_predictions] == ACTIONS
    assert len(all_predictions) == 9
    for prediction in all_predictions:
        assert_prediction_is_valid(prediction)

    print("Checking batched prediction and input order...")
    batch_predictions = predictor.predict_all_uplifts_batch(CONTEXTS)
    assert len(batch_predictions) == len(CONTEXTS)
    for context_index, predictions in enumerate(batch_predictions):
        assert [prediction.action for prediction in predictions] == ACTIONS
        expected = predictor.predict_all_uplifts(CONTEXTS[context_index])
        for batched, individual in zip(predictions, expected):
            assert batched.action == individual.action
            assert math.isclose(
                batched.treatment_probability,
                individual.treatment_probability,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            assert math.isclose(
                batched.control_probability,
                individual.control_probability,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            assert math.isclose(
                batched.uplift,
                individual.uplift,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            assert_prediction_is_valid(batched)

    assert batch_predictions[0][0].control_probability != batch_predictions[1][0].control_probability

    print("Checking unknown-action and missing-feature errors...")
    try:
        predictor.predict_uplift(CONTEXTS[0], "UNKNOWN_ACTION")
        raise AssertionError("Unknown action did not raise ValueError")
    except ValueError as error:
        assert "Unknown uplift action" in str(error)

    incomplete_context = CONTEXTS[0].copy()
    del incomplete_context["amount"]
    try:
        predictor.predict_all_uplifts(incomplete_context)
        raise AssertionError("Missing feature did not raise ValueError")
    except ValueError as error:
        assert "Missing uplift model features" in str(error)
        assert "amount" in str(error)

    print("Checking batch inference call count...")
    counting_predictor = UpliftPredictor()
    calls = Counter()
    counting_predictor.models = {
        action: CountingModel(model, action, calls)
        for action, model in counting_predictor.models.items()
    }
    counting_predictor.predict_all_uplifts_batch(CONTEXTS)
    assert sum(calls.values()) == len(ACTIONS)
    assert all(calls[action] == 1 for action in ACTIONS)
    print(f"Batch inference used {sum(calls.values())} predict_proba calls.")

    print("\nAll UpliftPredictor checks passed.")


if __name__ == "__main__":
    main()
