from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))


from backend.app.ml.recovery_predictor import RecoveryPredictor


ACTIONS = [
    "RETRY_NOW",
    "RETRY_LATER",
    "PAYMENT_LINK",
    "ALTERNATE_METHOD",
    "WHATSAPP",
    "EMAIL",
    "INCENTIVE",
    "HUMAN_ESCALATION",
    "DO_NOTHING",
]


def main():

    print("\nLoading recovery model...")

    predictor = RecoveryPredictor()

    print("Model loaded successfully.\n")

    context = {
        "amount": 2500.0,
        "payment_method": "UPI",
        "failure_code": "BANK_TIMEOUT",
        "failure_type": "TEMPORARY_BANK_FAILURE",
        "attempt_number": 1,
        "hour": 14,
        "day_of_week": 2,

        "customer_tenure_days": 500,
        "successful_payments": 12,
        "failed_payments": 3,
        "previous_recoveries": 2,
        "historical_recovery_rate": 0.67,
        "avg_transaction_value": 2200.0,

        "whatsapp_response_rate": 0.45,
        "email_response_rate": 0.30,
        "retry_success_rate": 0.75,
        "payment_link_conversion_rate": 0.40,
        "price_sensitivity": 0.50,
    }

    print("==============================")
    print("RECOVERY MODEL ACTION TEST")
    print("==============================")

    print(
        f"\nFailure type: "
        f"{context['failure_type']}"
    )

    print(
        f"Payment amount: "
        f"₹{context['amount']:,.2f}"
    )

    print(
        f"Attempt number: "
        f"{context['attempt_number']}"
    )

    print("\nPredicted recovery probabilities:\n")

    results = []

    for action in ACTIONS:

        probability = (
            predictor.predict_probability(
                context,
                action,
            )
        )

        results.append(
            (
                action,
                probability,
            )
        )

    results.sort(
        key=lambda item: item[1],
        reverse=True,
    )

    for action, probability in results:

        print(
            f"{action:20s} "
            f"-> {probability:.4f} "
            f"({probability:.2%})"
        )

    best_action, best_probability = (
        results[0]
    )

    print("\n------------------------------")

    print(
        f"Highest predicted action: "
        f"{best_action}"
    )

    print(
        f"Predicted recovery: "
        f"{best_probability:.2%}"
    )

    print("------------------------------")

    # Basic sanity checks

    assert len(results) == 9

    assert all(
        0 <= probability <= 1
        for _, probability in results
    )

    unique_probabilities = {
        round(probability, 6)
        for _, probability in results
    }

    assert len(unique_probabilities) > 1, (
        "All actions produced the same probability."
    )

    print("\nAll sanity checks passed.")


if __name__ == "__main__":
    main()