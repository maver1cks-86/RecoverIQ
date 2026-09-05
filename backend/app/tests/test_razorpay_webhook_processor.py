from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from sqlalchemy import delete
from app.models.outcome import Outcome
from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.models.customer import Customer
from app.models.decision import RecoveryDecision
from app.models.enums import (
    InterventionStatus,
    PaymentStatus,
    PolicyStatus,
)
from app.models.intervention import Intervention
from app.models.merchant import Merchant
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.services.razorpay_webhook_processor import RazorpayWebhookProcessor


def _cleanup() -> None:
    with SessionLocal() as db:
        db.execute(delete(WebhookEvent))
        db.execute(delete(Outcome))
        db.execute(delete(Intervention))
        db.execute(delete(RecoveryDecision))
        db.execute(delete(Payment))
        db.execute(delete(Customer))
        db.execute(delete(Merchant))
        db.commit()


def _seed_intervention() -> tuple[int, int]:
    with SessionLocal() as db:
        merchant = Merchant(
            name="Webhook Test Merchant",
        )
        db.add(merchant)
        db.flush()

        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id="cust_webhook_test_001",
)
        db.add(customer)
        db.flush()

        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            razorpay_payment_id="pay_original_test",
            amount=Decimal("100.00"),
            currency="INR",
            payment_method="card",
            status=PaymentStatus.FAILED,
            attempt_count=1,
        )
        db.add(payment)
        db.flush()

        decision = RecoveryDecision(
            payment_id=payment.id,
            selected_action=RecoveryAction.PAYMENT_LINK,
            predicted_probability=0.65,
            expected_value=Decimal("65.00"),
            policy_status=PolicyStatus.ALLOWED,
            model_version="test",
        )
        db.add(decision)
        db.flush()

        intervention = Intervention(
            decision_id=decision.id,
            action_type=RecoveryAction.PAYMENT_LINK,
            status=InterventionStatus.EXECUTED,
            provider="razorpay",
            provider_action_id="plink_processor_test_001",
            provider_status="created",
        )
        db.add(intervention)
        db.commit()

        return intervention.id, payment.id


def test_paid_webhook_marks_recovery_successful():
    _cleanup()

    try:
        intervention_id, payment_id = _seed_intervention()

        event_time = datetime.now(timezone.utc)

        with SessionLocal() as db:
            webhook = WebhookEvent(
                provider="razorpay",
                provider_event_id="evt_processor_paid_001",
                event_type="payment_link.paid",
                account_id="acc_test",
                payload={
                    "payment_link": {
                        "entity": {
                            "id": "plink_processor_test_001",
                            "status": "paid",
                            "amount_paid": 10000,
                        }
                    }
                },
                status="received",
                provider_created_at=event_time,
            )

            db.add(webhook)
            db.commit()
            db.refresh(webhook)

            result = RazorpayWebhookProcessor(db).process(webhook)

            assert result == "processed"

            db.refresh(webhook)

            intervention = db.get(
                Intervention,
                intervention_id,
            )
            payment = db.get(
                Payment,
                payment_id,
            )

            assert webhook.status == "processed"
            assert webhook.processed_at is not None

            assert intervention is not None
            assert intervention.status == InterventionStatus.SUCCEEDED
            assert intervention.provider_status == "paid"
            assert intervention.last_provider_event_at == event_time

            assert intervention.outcome is not None
            assert intervention.outcome.recovered is True
            assert intervention.outcome.recovered_amount == Decimal("100.00")

            assert payment is not None
            assert payment.status == PaymentStatus.RECOVERED

    finally:
        _cleanup()


def test_older_webhook_is_marked_stale():
    _cleanup()

    try:
        intervention_id, _ = _seed_intervention()

        newer_time = datetime.now(timezone.utc)
        older_time = newer_time - timedelta(minutes=10)

        with SessionLocal() as db:
            intervention = db.get(
                Intervention,
                intervention_id,
            )

            intervention.last_provider_event_at = newer_time
            intervention.provider_status = "paid"
            intervention.status = InterventionStatus.SUCCEEDED

            db.commit()

            webhook = WebhookEvent(
                provider="razorpay",
                provider_event_id="evt_processor_stale_001",
                event_type="payment_link.cancelled",
                account_id="acc_test",
                payload={
                    "payment_link": {
                        "entity": {
                            "id": "plink_processor_test_001",
                            "status": "cancelled",
                        }
                    }
                },
                status="received",
                provider_created_at=older_time,
            )

            db.add(webhook)
            db.commit()
            db.refresh(webhook)

            result = RazorpayWebhookProcessor(db).process(webhook)

            assert result == "stale"

            db.refresh(webhook)
            db.refresh(intervention)

            assert webhook.status == "stale"

            assert intervention.status == InterventionStatus.SUCCEEDED
            assert intervention.provider_status == "paid"
            assert intervention.last_provider_event_at == newer_time

    finally:
        _cleanup()


@pytest.mark.parametrize(
    ("event_type", "provider_status"),
    [
        ("payment_link.partially_paid", "partially_paid"),
        ("payment_link.cancelled", "cancelled"),
        ("payment_link.expired", "expired"),
    ],
)
def test_success_is_never_downgraded_by_later_events(event_type, provider_status):
    _cleanup()
    try:
        intervention_id, payment_id = _seed_intervention()
        paid_time = datetime.now(timezone.utc)
        with SessionLocal() as db:
            paid = WebhookEvent(provider="razorpay", provider_event_id=f"evt_paid_{event_type}", event_type="payment_link.paid", payload={"payment_link":{"entity":{"id":"plink_processor_test_001","status":"paid","amount_paid":10000}}}, status="received", provider_created_at=paid_time)
            db.add(paid); db.commit(); RazorpayWebhookProcessor(db).process(paid)
            later = WebhookEvent(provider="razorpay", provider_event_id=f"evt_later_{event_type}", event_type=event_type, payload={"payment_link":{"entity":{"id":"plink_processor_test_001","status":provider_status,"amount_paid":5000}}}, status="received", provider_created_at=paid_time + timedelta(minutes=1))
            db.add(later); db.commit(); assert RazorpayWebhookProcessor(db).process(later) == "processed"
            intervention = db.get(Intervention, intervention_id); payment = db.get(Payment, payment_id)
            assert intervention.status is InterventionStatus.SUCCEEDED
            assert intervention.provider_status == "paid"
            assert intervention.outcome.recovered is True
            assert intervention.outcome.recovered_amount == Decimal("100.00")
            assert payment.status is PaymentStatus.RECOVERED
    finally: _cleanup()


def test_equal_timestamp_uses_terminal_event_precedence():
    _cleanup()
    try:
        intervention_id, _ = _seed_intervention(); event_time = datetime.now(timezone.utc)
        with SessionLocal() as db:
            paid = WebhookEvent(provider="razorpay", provider_event_id="evt_equal_paid", event_type="payment_link.paid", payload={"payment_link":{"entity":{"id":"plink_processor_test_001","status":"paid","amount_paid":10000}}}, status="received", provider_created_at=event_time)
            db.add(paid); db.commit(); RazorpayWebhookProcessor(db).process(paid)
            cancelled = WebhookEvent(provider="razorpay", provider_event_id="evt_equal_cancelled", event_type="payment_link.cancelled", payload={"payment_link":{"entity":{"id":"plink_processor_test_001","status":"cancelled"}}}, status="received", provider_created_at=event_time)
            db.add(cancelled); db.commit(); assert RazorpayWebhookProcessor(db).process(cancelled) == "stale"
            assert db.get(Intervention, intervention_id).status is InterventionStatus.SUCCEEDED
    finally: _cleanup()
