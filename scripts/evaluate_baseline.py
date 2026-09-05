from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "backend"))
sys.path.append(str(ROOT / "scripts"))

from backend.app.decision.baseline import (
    CUSTOMER_CONTACT_ACTIONS,
    RETRY_ACTIONS,
    choose_baseline_action,
)

from generate_dateset import (
    ACTION_COSTS,
    calculate_incentive,
    calculate_recovery_probability,
)


SEED = 42

INPUT_PATH = ROOT / "data" / "processed" / "test.csv"

DECISIONS_PATH = (
    ROOT
    / "data"
    / "processed"
    / "baseline_decisions.csv"
)

METRICS_PATH = (
    ROOT
    / "data"
    / "processed"
    / "baseline_metrics.json"
)


def row_to_customer(row):
    return {
        "customer_id": row["customer_id"],
        "customer_tenure_days":
            row["customer_tenure_days"],
        "successful_payments":
            row["successful_payments"],
        "failed_payments":
            row["failed_payments"],
        "previous_recoveries":
            row["previous_recoveries"],
        "historical_recovery_rate":
            row["historical_recovery_rate"],
        "avg_transaction_value":
            row["avg_transaction_value"],
        "whatsapp_response_rate":
            row["whatsapp_response_rate"],
        "email_response_rate":
            row["email_response_rate"],
        "retry_success_rate":
            row["retry_success_rate"],
        "payment_link_conversion_rate":
            row["payment_link_conversion_rate"],
        "price_sensitivity":
            row["price_sensitivity"],
    }


def row_to_payment(row):
    return {
        "amount": row["amount"],
        "payment_method": row["payment_method"],
        "failure_type": row["failure_type"],
        "failure_code": row["failure_code"],
        "attempt_number": row["attempt_number"],
        "hour": row["hour"],
        "day_of_week": row["day_of_week"],
    }


def evaluate_baseline(df):
    rng = np.random.default_rng(SEED)

    results = []

    for _, row in df.iterrows():

        decision = choose_baseline_action(
            row["failure_type"],
            int(row["attempt_number"]),
        )

        action = decision.action

        customer = row_to_customer(row)
        payment = row_to_payment(row)

        probability = (
            calculate_recovery_probability(
                customer,
                payment,
                action,
                add_noise=False,
            )
        )

        recovered = (
            rng.random() < probability
        )

        intervention_cost = (
            ACTION_COSTS[action]
        )

        incentive_cost = (
            calculate_incentive(
                action,
                row["amount"],
            )
        )

        recovered_amount = (
            float(row["amount"])
            if recovered
            else 0.0
        )

        expected_gross_value = (
            probability
            * float(row["amount"])
        )

        expected_net_value = (
            expected_gross_value
            - intervention_cost
            - incentive_cost
        )

        results.append({
            "payment_id":
                int(row["payment_id"]),

            "amount":
                float(row["amount"]),

            "failure_type":
                row["failure_type"],

            "baseline_action":
                action,

            "baseline_reason":
                decision.reason,

            "recovery_probability":
                probability,

            "recovered":
                int(recovered),

            "recovered_amount":
                recovered_amount,

            "intervention_cost":
                intervention_cost,

            "incentive_cost":
                incentive_cost,

            "expected_gross_value":
                expected_gross_value,

            "expected_net_value":
                expected_net_value,
        })

    return pd.DataFrame(results)


def calculate_metrics(df):

    revenue_at_risk = df["amount"].sum()

    gross_recovered = (
        df["recovered_amount"].sum()
    )

    intervention_spend = (
        df["intervention_cost"].sum()
    )

    incentive_spend = (
        df["incentive_cost"].sum()
    )

    total_spend = (
        intervention_spend
        + incentive_spend
    )

    net_recovered = (
        gross_recovered
        - total_spend
    )

    expected_net = (
        df["expected_net_value"].sum()
    )

    recovery_rate = (
        df["recovered"].mean()
    )

    retry_count = (
        df["baseline_action"]
        .isin(RETRY_ACTIONS)
        .sum()
    )

    customer_contacts = (
        df["baseline_action"]
        .isin(CUSTOMER_CONTACT_ACTIONS)
        .sum()
    )

    do_nothing_count = (
        (
            df["baseline_action"]
            == "DO_NOTHING"
        )
        .sum()
    )

    return {
        "system":
            "RecoverIQ synthetic fixed-rule baseline",

        "payments_evaluated":
            int(len(df)),

        "total_revenue_at_risk":
            round(float(revenue_at_risk), 2),

        "gross_recovered_revenue":
            round(float(gross_recovered), 2),

        "recovery_rate":
            round(float(recovery_rate), 4),

        "intervention_spend":
            round(float(intervention_spend), 2),

        "incentive_spend":
            round(float(incentive_spend), 2),

        "net_recovered_revenue":
            round(float(net_recovered), 2),

        "expected_net_recovered_revenue":
            round(float(expected_net), 2),

        "retry_count":
            int(retry_count),

        "customer_contacts":
            int(customer_contacts),

        "do_nothing_count":
            int(do_nothing_count),
    }


def main():

    df = pd.read_csv(INPUT_PATH)

    decisions = evaluate_baseline(df)

    metrics = calculate_metrics(
        decisions
    )

    decisions.to_csv(
        DECISIONS_PATH,
        index=False,
    )

    with open(
        METRICS_PATH,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics,
            file,
            indent=4,
        )

    print("\nBASELINE RESULTS\n")

    for key, value in metrics.items():
        print(f"{key}: {value}")

    print("\nAction distribution:\n")

    print(
        decisions[
            "baseline_action"
        ].value_counts()
    )


if __name__ == "__main__":
    main()