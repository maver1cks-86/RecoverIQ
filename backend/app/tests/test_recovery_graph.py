from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.models.customer import Customer
from app.models.decision import RecoveryDecision
from app.models.enums import InterventionStatus, PaymentStatus
from app.models.intervention import Intervention
from app.models.merchant import Merchant
from app.models.outcome import Outcome
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.orchestration.nodes import RecoveryWorkflowError
from app.orchestration.recovery_graph import run_recovery_workflow
from app.services.recovery_service import RecoveryExecutionResult
from app.tasks.recovery_tasks import run_recovery_workflow_task


def cleanup_test_data() -> None:
    with SessionLocal() as db:
        db.execute(delete(WebhookEvent))
        db.execute(delete(Outcome))
        db.execute(delete(Intervention))
        db.execute(delete(RecoveryDecision))
        db.execute(delete(Payment))
        db.execute(delete(Customer))
        db.execute(delete(Merchant))
        db.commit()


def seed_failed_payment() -> int:
    with SessionLocal() as db:
        merchant = Merchant(name="Recovery Graph Test Merchant")
        db.add(merchant)
        db.flush()

        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id="cust_graph_001",
            successful_payments=8,
            failed_payments=3,
            previous_recoveries=1,
            avg_transaction_value=Decimal("1200.00"),
        )
        db.add(customer)
        db.flush()

        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            razorpay_payment_id="pay_graph_001",
            amount=Decimal("1000.00"),
            currency="INR",
            payment_method="card",
            status=PaymentStatus.FAILED,
            failure_code="BANK_TIMEOUT",
            failure_reason="Temporary bank timeout",
            attempt_count=1,
        )
        db.add(payment)
        db.commit()
        return payment.id


class SuccessfulRecoveryService:
    def __init__(self):
        self.calls = []

    async def execute_payment_link(self, **kwargs):
        self.calls.append(kwargs)
        return RecoveryExecutionResult(
            provider="razorpay",
            action="PAYMENT_LINK",
            success=True,
            provider_action_id="plink_graph_001",
            payment_url="https://rzp.io/i/graph001",
            status="created",
            reference_id="ri_graph_001",
        )


class FailingRecoveryService:
    def __init__(self):
        self.call_count = 0

    async def execute_payment_link(self, **kwargs):
        self.call_count += 1
        raise RuntimeError("Temporary provider failure")


@pytest.fixture(autouse=True)
def clean_database():
    cleanup_test_data()
    yield
    cleanup_test_data()


def run_planned(payment_id: int, action: str, assignment_id: int = 101, **kwargs):
    return run_recovery_workflow(
        payment_id,
        planned_action=action,
        optimization_assignment_id=assignment_id,
        planned_policy_status="ALLOWED",
        planned_probability=0.62,
        planned_expected_value=619.5,
        planned_incremental_value=199.5 if action != "DO_NOTHING" else 0.0,
        planned_intervention_cost=0.5 if action != "DO_NOTHING" else 0.0,
        **kwargs,
    )


def test_graph_preserves_persisted_planned_action(monkeypatch):
    payment_id = seed_failed_payment()

    result = run_planned(payment_id, "RETRY_LATER")

    assert result["selected_action"] == "RETRY_LATER"
    assert result["execution_status"] == "PLANNED"
    assert result["next_step"] == "END"
    assert result["decision_id"] is not None
    assert result["intervention_id"] is not None


def test_do_nothing_path_persists_decision_without_intervention(monkeypatch):
    payment_id = seed_failed_payment()
    result = run_planned(payment_id, "DO_NOTHING")

    assert result["execution_status"] == "DO_NOTHING"
    assert result["decision_id"] is not None
    assert result["intervention_id"] is None

    with SessionLocal() as db:
        assert db.scalar(select(func.count(Intervention.id))) == 0


def test_payment_link_calls_service_and_persists_provider_id(monkeypatch):
    payment_id = seed_failed_payment()
    service = SuccessfulRecoveryService()
    monkeypatch.setattr(
        "app.orchestration.nodes.get_recovery_service",
        lambda: service,
    )

    result = run_planned(payment_id, "PAYMENT_LINK")

    assert len(service.calls) == 1
    assert service.calls[0]["original_payment_id"] == "pay_graph_001"
    assert result["execution_status"] == "EXECUTED"
    assert result["provider_action_id"] == "plink_graph_001"

    with SessionLocal() as db:
        intervention = db.get(Intervention, result["intervention_id"])
        assert intervention is not None
        assert intervention.status == InterventionStatus.EXECUTED
        assert intervention.provider == "razorpay"
        assert intervention.provider_action_id == "plink_graph_001"
        assert intervention.provider_status == "created"
        assert intervention.executed_at is not None


def test_execution_retry_stops_at_max_retries(monkeypatch):
    payment_id = seed_failed_payment()
    service = FailingRecoveryService()
    monkeypatch.setattr(
        "app.orchestration.nodes.get_recovery_service",
        lambda: service,
    )

    result = run_planned(payment_id, "PAYMENT_LINK", max_retries=2)

    assert service.call_count == 3
    assert result["retry_count"] == 3
    assert result["execution_status"] == "FAILED"
    assert result["next_step"] == "END"
    assert result["error"] == "Temporary provider failure"


def test_missing_payment_fails_clearly(monkeypatch):
    with pytest.raises(RecoveryWorkflowError, match="Payment 999999999 was not found"):
        run_planned(999999999, "DO_NOTHING")


def test_graph_rejects_unplanned_single_payment_redecision():
    payment_id = seed_failed_payment()
    with pytest.raises(ValueError, match="persisted optimization assignment"):
        run_recovery_workflow(payment_id)


def test_graph_replay_does_not_duplicate_intervention(monkeypatch):
    payment_id = seed_failed_payment()
    first = run_planned(payment_id, "EMAIL")
    second = run_planned(payment_id, "EMAIL")

    assert second["decision_id"] == first["decision_id"]
    assert second["intervention_id"] == first["intervention_id"]

    with SessionLocal() as db:
        assert db.scalar(select(func.count(RecoveryDecision.id))) == 1
        assert db.scalar(select(func.count(Intervention.id))) == 1


def test_celery_recovery_task_runs_synchronously(monkeypatch):
    expected = {
        "payment_id": 123,
        "selected_action": "DO_NOTHING",
        "execution_status": "DO_NOTHING",
        "next_step": "END",
    }
    monkeypatch.setattr(
        "app.tasks.recovery_tasks.execute_recovery_assignment_task.run",
        lambda assignment_id: expected,
    )

    result = run_recovery_workflow_task.run(123)

    assert result == expected


def test_unsupported_action_is_not_marked_successful(monkeypatch):
    payment_id = seed_failed_payment()
    result = run_planned(payment_id, "WHATSAPP")

    assert result["execution_status"] == "PLANNED"
    assert result["provider"] is None
    assert result["provider_action_id"] is None

    with SessionLocal() as db:
        intervention = db.get(Intervention, result["intervention_id"])
        assert intervention is not None
        assert intervention.status == InterventionStatus.PLANNED
        assert intervention.executed_at is None
