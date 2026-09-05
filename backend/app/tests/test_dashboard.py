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
from app.models.outcome import Outcome
from app.models.payment import Payment


client = TestClient(app)


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(Outcome))
        db.execute(delete(Intervention))
        db.execute(delete(RecoveryDecision))
        db.execute(delete(Payment))
        db.execute(delete(Customer))
        db.execute(delete(Merchant))
        db.commit()


def test_dashboard_empty_live_portfolio() -> None:
    _cleanup()
    response = client.get("/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["portfolio"]["failed_payments"] == 0
    assert data["portfolio"]["revenue_at_risk"] == "0.00"
    assert len(data["intervention_mix"]) == 9
    assert data["recent_interventions"] == []
    assert data["recent_recoveries"] == []
    assert data["offline_evaluation"]["label"] == (
        "OFFLINE / FROZEN TEST SET EVALUATION"
    )


def test_dashboard_aggregates_live_data_and_frozen_evaluation() -> None:
    _cleanup()
    try:
        with SessionLocal() as db:
            merchant = Merchant(name="Dashboard Test Merchant")
            db.add(merchant)
            db.flush()
            customer = Customer(
                merchant_id=merchant.id,
                external_customer_id="dashboard-test-customer",
            )
            db.add(customer)
            db.flush()
            payment = Payment(
                merchant_id=merchant.id,
                customer_id=customer.id,
                amount=Decimal("10.00"),
                currency="INR",
                payment_method="card",
                status=PaymentStatus.RECOVERED,
                attempt_count=1,
            )
            db.add(payment)
            db.flush()
            decision = RecoveryDecision(
                payment_id=payment.id,
                selected_action=RecoveryAction.PAYMENT_LINK,
                predicted_probability=0.65,
                expected_value=Decimal("4.25"),
                policy_status=PolicyStatus.ALLOWED,
                model_version="dashboard-test",
            )
            db.add(decision)
            db.flush()
            intervention = Intervention(
                decision_id=decision.id,
                action_type=RecoveryAction.PAYMENT_LINK,
                status=InterventionStatus.SUCCEEDED,
                provider="razorpay",
                provider_status="paid",
            )
            db.add(intervention)
            db.flush()
            db.add(
                Outcome(
                    intervention_id=intervention.id,
                    recovered=True,
                    recovered_amount=Decimal("10.00"),
                )
            )
            db.commit()

        response = client.get("/dashboard/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"]["recovered_payments"] == 1
        assert data["portfolio"]["recovered_revenue"] == "10.00"
        assert data["portfolio"]["recovery_rate"] == 100.0
        assert data["recent_interventions"][0]["provider"] == "razorpay"
        assert data["recent_recoveries"][0]["recovered_amount"] == "10.00"

        strategies = {
            item["strategy"]: item
            for item in data["offline_evaluation"]["strategies"]
        }
        assert strategies["BASELINE"]["net_value"] == "12414072.72"
        assert strategies["ML_DECISION"]["uplift_percent"] == 7.02
        assert strategies["OPTIMIZED"]["net_value"] == "12928146.30"
        assert data["offline_evaluation"]["solver_status"] == "OPTIMAL"
    finally:
        _cleanup()
