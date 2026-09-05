from __future__ import annotations

from unittest.mock import patch

import redis
from fastapi.testclient import TestClient

from app.main import app
from app.services.batch_event_service import BatchStatusEvent, publish_batch_event


client = TestClient(app)
CURRENT = {
    "total_budget": 2000,
    "incentive_budget": 1000,
    "max_retries": 350,
    "max_contacts": 300,
    "max_whatsapp": 150,
    "max_incentive_actions": 50,
    "max_human_escalations": 30,
    "solver_timeout_ms": 30000,
}


def test_batch_event_schema_has_typed_recovery_fields() -> None:
    event = BatchStatusEvent(
        type="payment.updated",
        batch_id=103,
        payment_id=971,
        assignment_id=534,
        status="RECOVERED",
        execution_status="RECOVERED",
        provider_status="paid",
        recovered_amount=1355.78,
    )
    assert event.model_dump()["recovered_amount"] == 1355.78


def test_websocket_stream_sends_typed_batch_event(monkeypatch) -> None:
    async def one_event(batch_id: int):
        yield BatchStatusEvent(
            type="assignment.updated",
            batch_id=batch_id,
            payment_id=971,
            execution_status="EXECUTING",
        ).model_dump(mode="json")

    monkeypatch.setattr("app.api.batch_stream.subscribe_batch_events", one_event)
    with client.websocket_connect("/ws/batches/103") as socket:
        message = socket.receive_json()
    assert message == {
        "type": "assignment.updated",
        "batch_id": 103,
        "payment_id": 971,
        "assignment_id": None,
        "status": None,
        "execution_status": "EXECUTING",
        "provider_status": None,
        "provider_action_id": None,
        "recovered_amount": None,
    }


def test_notification_failure_never_breaks_committed_work() -> None:
    with patch(
        "app.services.batch_event_service.redis.Redis.from_url",
        side_effect=redis.RedisError("offline"),
    ):
        assert publish_batch_event(
            BatchStatusEvent(type="batch.updated", batch_id=103, status="READY")
        ) is False


def post_parse(prompt: str):
    return client.post(
        "/copilot/what-if/parse",
        json={"prompt": prompt, "current_constraints": CURRENT},
    )


def test_what_if_returns_preview_without_applying_or_optimizing() -> None:
    parsed = {"total_budget": 250, "max_retries": 40, "max_contacts": 35}
    with patch(
        "app.api.copilot.GroundedLLMProvider.parse_what_if_constraints",
        return_value=parsed,
    ), patch("app.services.optimization_service.run_optimization") as optimize:
        response = post_parse("Limit spend to 250, retries to 40, contacts to 35")
    assert response.status_code == 200
    assert response.json()["proposed_changes"] == parsed
    assert response.json()["requires_confirmation"] is True
    assert response.json()["applied"] is False
    optimize.assert_not_called()


def test_what_if_rejects_negative_and_unknown_constraints() -> None:
    for parsed in ({"total_budget": -1}, {"unknown_capacity": 5}):
        with patch(
            "app.api.copilot.GroundedLLMProvider.parse_what_if_constraints",
            return_value=parsed,
        ):
            response = post_parse("invalid proposal")
        assert response.status_code == 422


def test_what_if_unavailable_fails_safe_without_inventing_values() -> None:
    with patch(
        "app.api.copilot.GroundedLLMProvider.parse_what_if_constraints",
        return_value=None,
    ):
        response = post_parse("change something")
    assert response.status_code == 503
    assert "no constraints were applied" in response.json()["detail"]
