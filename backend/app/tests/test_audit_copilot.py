from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.main import app
from app.models.customer import Customer
from app.models.decision import RecoveryDecision
from app.models.enums import InterventionStatus, PaymentStatus, PolicyStatus
from app.models.intervention import Intervention
from app.models.merchant import Merchant
from app.models.outcome import Outcome
from app.models.payment import Payment
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch, RecoveryBatchPayment
from app.models.webhook_event import WebhookEvent


client = TestClient(app)


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(OptimizationAssignment)); db.execute(delete(OptimizationPlan))
        db.execute(delete(RecoveryBatchPayment)); db.execute(delete(RecoveryBatch))
        db.execute(delete(WebhookEvent))
        db.execute(delete(Outcome)); db.execute(delete(Intervention)); db.execute(delete(RecoveryDecision))
        db.execute(delete(Payment)); db.execute(delete(Customer)); db.execute(delete(Merchant)); db.commit()


def _seed_payment() -> int:
    with SessionLocal() as db:
        merchant = Merchant(name="Phase 26 Test Merchant"); db.add(merchant); db.flush()
        customer = Customer(merchant_id=merchant.id, external_customer_id="phase-26-customer"); db.add(customer); db.flush()
        payment = Payment(merchant_id=merchant.id, customer_id=customer.id, amount=Decimal("10.00"), currency="INR", payment_method="upi", status=PaymentStatus.RECOVERED, failure_code="BAD_REQUEST_ERROR", failure_reason="test failure", attempt_count=1); db.add(payment); db.flush()
        decision = RecoveryDecision(payment_id=payment.id, selected_action=RecoveryAction.PAYMENT_LINK, predicted_probability=.71, expected_value=Decimal("5.40"), policy_status=PolicyStatus.ALLOWED, model_version="phase-26-test"); db.add(decision); db.flush()
        intervention = Intervention(decision_id=decision.id, action_type=RecoveryAction.PAYMENT_LINK, status=InterventionStatus.SUCCEEDED, provider="razorpay", provider_action_id="plink_phase26", provider_status="paid", intervention_cost=Decimal("0.50")); db.add(intervention); db.flush()
        db.add(Outcome(intervention_id=intervention.id, recovered=True, recovered_amount=Decimal("10.00"))); db.commit(); return payment.id


def test_audit_missing_payment_is_clear() -> None:
    _cleanup()
    assert client.get("/audit/payments/999999999").status_code == 404


def test_audit_returns_only_persisted_ordered_events() -> None:
    _cleanup()
    try:
        payment_id = _seed_payment()
        data = client.get(f"/audit/payments/{payment_id}").json()
        assert data["source"] == "LIVE_SYSTEM_DATABASE"
        assert [event["event_type"] for event in data["events"]] == ["PAYMENT", "DECISION", "POLICY", "INTERVENTION", "OUTCOME"]
        assert all(event["event_type"] != "WEBHOOK" for event in data["events"])
        assert data["events"][1]["details"]["predicted_probability"] == .71
    finally:
        _cleanup()


def test_audit_serializes_nested_portfolio_evidence() -> None:
    _cleanup()
    try:
        payment_id = _seed_payment()
        with SessionLocal() as db:
            payment = db.get(Payment, payment_id)
            batch = RecoveryBatch(
                merchant_id=payment.merchant_id,
                source="TEST",
                reference_id=f"audit-nested-{payment_id}",
                status="READY",
                payment_count=1,
                revenue_at_risk=payment.amount,
            )
            db.add(batch); db.flush()
            db.add(RecoveryBatchPayment(batch_id=batch.id, payment_id=payment_id))
            plan = OptimizationPlan(
                batch_id=batch.id,
                version=1,
                solver_status="OPTIMAL",
                objective_value=Decimal("4.90"),
                expected_net_value=Decimal("5.40"),
                constraints_snapshot={"max_contacts": 3, "enabled_actions": ["PAYMENT_LINK", "DO_NOTHING"]},
                resource_usage=[],
                model_version="audit-regression",
            )
            db.add(plan); db.flush()
            db.add(OptimizationAssignment(
                plan_id=plan.id,
                payment_id=payment_id,
                selected_action=RecoveryAction.PAYMENT_LINK,
                policy_status=PolicyStatus.ALLOWED,
                recovery_probability=.71,
                expected_value=Decimal("5.40"),
                incremental_value=Decimal("4.90"),
                intervention_cost=Decimal("0.50"),
                incentive_cost=Decimal("0.00"),
                alternatives=[{"action": "PAYMENT_LINK", "rank": 1, "incremental_value": 4.9}],
                policy_evidence=[{"action": "PAYMENT_LINK", "allowed": True}],
            ))
            db.commit()
        response = client.get(f"/audit/payments/{payment_id}")
        assert response.status_code == 200
        plan_event = next(event for event in response.json()["events"] if event["event_type"] == "PLAN")
        assert plan_event["details"]["alternatives"][0]["action"] == "PAYMENT_LINK"
        assert plan_event["details"]["constraints_snapshot"]["enabled_actions"][-1] == "DO_NOTHING"
    finally:
        _cleanup()


def test_copilot_falls_back_without_llm_and_never_executes() -> None:
    _cleanup()
    try:
        payment_id = _seed_payment()
        with patch.object(settings, "LLM_API_KEY", ""), patch("app.integrations.razorpay.client.RazorpayClient.create_payment_link") as execute:
            response = client.post("/copilot/chat", json={"message": f"What happened to payment {payment_id}?", "context": {"payment_id": payment_id}})
        assert response.status_code == 200
        data = response.json()
        assert data["ai_available"] is False
        assert data["data_scope"] == "LIVE SYSTEM / DATABASE DATA"
        assert str(payment_id) in data["answer"]
        assert "get_audit_trace" in data["tools_used"]
        assert settings.RAZORPAY_KEY_SECRET not in response.text if settings.RAZORPAY_KEY_SECRET else True
        execute.assert_not_called()
    finally:
        _cleanup()


def test_copilot_status_is_graceful_without_llm() -> None:
    with patch.object(settings, "LLM_API_KEY", ""):
        assert client.get("/copilot/status").json() == {"ai_available": False, "provider": "not_configured", "deterministic_explanations": True}


def test_audit_maps_only_the_matching_persisted_webhook() -> None:
    _cleanup()
    try:
        payment_id = _seed_payment()
        with SessionLocal() as db:
            db.add(WebhookEvent(provider="razorpay", provider_event_id="evt_phase26", event_type="payment_link.paid", payload={"payment_link": {"entity": {"id": "plink_phase26"}}}, status="processed", provider_created_at=datetime.now(timezone.utc)))
            db.add(WebhookEvent(provider="razorpay", provider_event_id="evt_unrelated", event_type="payment_link.paid", payload={"payment_link": {"entity": {"id": "plink_other"}}}, status="processed"))
            db.commit()
        events = client.get(f"/audit/payments/{payment_id}").json()["events"]
        webhooks = [event for event in events if event["event_type"] == "WEBHOOK"]
        assert len(webhooks) == 1
        assert webhooks[0]["details"] == {"event_type": "payment_link.paid", "provider_event_id": "evt_phase26", "provider_action_id": "plink_phase26"}
    finally:
        _cleanup()


def test_copilot_is_read_only_for_constraints_and_persisted_records() -> None:
    _cleanup()
    try:
        payment_id = _seed_payment()
        with SessionLocal() as db:
            before = db.query(Intervention).count()
        response = client.post("/copilot/chat", json={"message": "Change the recovery budget and contact limit", "context": {"page": "optimization"}})
        assert response.status_code == 200
        with SessionLocal() as db:
            assert db.query(Intervention).count() == before
            assert db.get(Payment, payment_id).status is PaymentStatus.RECOVERED
    finally:
        _cleanup()
