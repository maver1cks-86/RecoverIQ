from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))


from app.decision.action_evaluator import ActionEvaluator


def main():

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

    evaluator = ActionEvaluator()

    results = evaluator.evaluate(
        context
    )

    results = sorted(
        results,
        key=lambda item:
            item.recovery_probability,
        reverse=True,
    )

    print("\n==============================")
    print("CANDIDATE ACTION EVALUATION")
    print("==============================\n")

    for result in results:

        print(
            f"{result.action:20s}"
            f" -> "
            f"{result.recovery_probability:.4f}"
            f" "
            f"({result.recovery_probability:.2%})"
        )

    assert len(results) == 9

    assert all(
        0 <= result.recovery_probability <= 1
        for result in results
    )

    print(
        "\nAll candidate actions "
        "evaluated successfully."
    )


if __name__ == "__main__":
    main()