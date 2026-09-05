from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


VALID_CONSTRAINTS = {
    "total_budget": 2000,
    "incentive_budget": 1000,
    "max_retries": 350,
    "max_contacts": 300,
    "max_whatsapp": 150,
    "max_incentive_actions": 50,
    "max_human_escalations": 30,
    "solver_timeout_ms": 30000,
}


def test_optimization_rejects_negative_constraints() -> None:
    response = client.post(
        "/optimization/run",
        json={**VALID_CONSTRAINTS, "total_budget": -1},
    )
    assert response.status_code == 422


def test_real_optimization_returns_feasible_plan_without_execution() -> None:
    with patch(
        "app.integrations.razorpay.client.RazorpayClient.create_payment_link"
    ) as create_payment_link:
        response = client.post("/optimization/run", json=VALID_CONSTRAINTS)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"OPTIMAL", "FEASIBLE"}
    assert data["portfolio_source"] == "FROZEN_DEMO_PORTFOLIO"
    assert len(data["assignments"]) == data["payment_count"] == 1000
    assert len({item["payment_id"] for item in data["assignments"]}) == 1000
    assert sum(item["count"] for item in data["action_allocation"]) == 1000
    assert all(item["within_constraint"] for item in data["resource_usage"])
    create_payment_link.assert_not_called()


def test_tighter_capacity_changes_real_allocation() -> None:
    default = client.post("/optimization/run", json=VALID_CONSTRAINTS).json()
    tight = client.post(
        "/optimization/run",
        json={
            **VALID_CONSTRAINTS,
            "total_budget": 250,
            "max_retries": 40,
            "max_contacts": 35,
            "max_whatsapp": 10,
            "max_incentive_actions": 2,
            "max_human_escalations": 2,
        },
    ).json()
    default_counts = {
        item["action"]: item["count"] for item in default["action_allocation"]
    }
    tight_counts = {
        item["action"]: item["count"] for item in tight["action_allocation"]
    }
    assert default_counts != tight_counts
    assert tight_counts["DO_NOTHING"] > default_counts["DO_NOTHING"]
    assert all(item["within_constraint"] for item in tight["resource_usage"])
