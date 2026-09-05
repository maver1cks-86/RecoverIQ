from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.main import app
from app.models.customer import Customer
from app.models.decision import RecoveryDecision
from app.models.enums import InterventionStatus, PaymentStatus, PolicyStatus
from app.models.intervention import Intervention
from app.models.merchant import Merchant
from app.models.payment import Payment
from app.models.recovery_batch import OptimizationAssignment, OptimizationPlan, RecoveryBatch, RecoveryBatchPayment


client = TestClient(app)


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(OptimizationAssignment)); db.execute(delete(OptimizationPlan))
        db.execute(delete(RecoveryBatchPayment)); db.execute(delete(RecoveryBatch))
        db.execute(delete(Intervention)); db.execute(delete(RecoveryDecision))
        db.execute(delete(Payment)); db.execute(delete(Customer)); db.execute(delete(Merchant)); db.commit()


def test_intervention_ledger_lists_and_filters_persisted_rows() -> None:
    _cleanup()
    try:
        with SessionLocal() as db:
            merchant = Merchant(name="Intervention Ledger Test"); db.add(merchant); db.flush()
            customer = Customer(merchant_id=merchant.id, external_customer_id="ledger-test"); db.add(customer); db.flush()
            payment = Payment(merchant_id=merchant.id, customer_id=customer.id, amount=Decimal("100.00"), currency="INR", payment_method="upi", status=PaymentStatus.FAILED, attempt_count=1); db.add(payment); db.flush()
            decision = RecoveryDecision(payment_id=payment.id, selected_action=RecoveryAction.PAYMENT_LINK, predicted_probability=.7, expected_value=Decimal("69.50"), policy_status=PolicyStatus.ALLOWED, model_version="test"); db.add(decision); db.flush()
            intervention = Intervention(decision_id=decision.id, action_type=RecoveryAction.PAYMENT_LINK, status=InterventionStatus.EXECUTED, provider="razorpay", provider_action_id="plink_ledger_test", provider_status="created", intervention_cost=Decimal("0.50"), executed_at=datetime.now(timezone.utc)); db.add(intervention); db.commit()
            payment_id = payment.id

        response = client.get(f"/interventions?provider=razorpay&search={payment_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["provider_action_id"] == "plink_ledger_test"
        assert data["items"][0]["payment_id"] == payment_id
    finally:
        _cleanup()
