from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.evaluation_service import STRATEGY_ASSIGNMENTS


client = TestClient(app)


def test_evaluation_summary_returns_exact_frozen_metrics() -> None:
    response = client.get("/evaluation/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["dataset"] == {"type": "synthetic", "role": "frozen_held_out_test", "total_records": 50000, "train_records": 32000, "validation_records": 8000, "test_records": 10000}
    assert data["baseline"]["net_recovery"] == 12414072.72
    assert data["baseline"]["recovery_rate"] == 0.5029
    assert data["unconstrained_ml"]["net_recovery"] == 13285455.82
    assert data["recoveriq"]["net_recovery"] == 12928146.30
    assert data["recoveriq"]["improvement"] == 514073.58
    assert data["recoveriq"]["relative_improvement_percent"] == 4.14
    assert data["recoveriq"]["solver_status"] == "OPTIMAL"
    assert data["scale_benchmarks"][2]["status"] == "FEASIBLE"


def test_evaluation_assignments_are_paginated_from_read_only_artifact() -> None:
    before = Path(STRATEGY_ASSIGNMENTS).stat().st_mtime_ns
    response = client.get("/evaluation/assignments", params={"page": 2, "page_size": 3, "action": "RETRY_LATER"})
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert len(data["items"]) == 3
    assert all(item["action"] == "RETRY_LATER" for item in data["items"])
    assert data["columns"] == ["payment_id", "strategy", "action", "amount", "true_recovery_probability", "expected_gross_revenue", "expected_net_revenue", "intervention_cost", "incentive_cost"]
    assert Path(STRATEGY_ASSIGNMENTS).stat().st_mtime_ns == before


def test_frozen_assignment_artifact_has_three_strategies_for_10000_payments() -> None:
    response = client.get("/evaluation/assignments", params={"page": 1, "page_size": 1})
    assert response.status_code == 200
    assert response.json()["total"] == 30000
