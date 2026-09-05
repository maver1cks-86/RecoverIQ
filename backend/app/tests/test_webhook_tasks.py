from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete

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
from app.models.outcome import Outcome
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.tasks.webhook_tasks import process_razorpay_webhook


TEST_PAYMENT_LINK_ID = "plink_task_test_001"


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


def seed_webhook(*, webhook_status: str = "received") -> tuple[int, int]:
    with SessionLocal() as db:
        merchant = Merchant(name="Webhook Task Test Merchant")
        db.add(merchant)
        db.flush()

        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id="cust_webhook_task_001",
        )
        db.add(customer)
        db.flush()

        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            razorpay_payment_id="pay_webhook_task_original",
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
            provider_action_id=TEST_PAYMENT_LINK_ID,
            provider_status="created",
        )
        db.add(intervention)

        webhook = WebhookEvent(
            provider="razorpay",
            provider_event_id=f"event_task_{webhook_status}",
            event_type="payment_link.paid",
            account_id="acc_task_test",
            payload={
                "payment_link": {
                    "entity": {
                        "id": TEST_PAYMENT_LINK_ID,
                        "status": "paid",
                        "amount": 10000,
                        "amount_paid": 10000,
                        "currency": "INR",
                    }
                }
            },
            status=webhook_status,
            provider_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db.add(webhook)
        db.commit()

        return webhook.id, intervention.id


def test_queued_webhook_task_processes_payment_link_paid():
    cleanup_test_data()

    try:
        webhook_id, intervention_id = seed_webhook()

        result = process_razorpay_webhook.run(webhook_id)

        assert result["status"] == "processed"
        assert result["processing_status"] == "processed"

        with SessionLocal() as db:
            webhook = db.get(WebhookEvent, webhook_id)
            intervention = db.get(Intervention, intervention_id)

            assert webhook is not None
            assert webhook.status == "processed"
            assert webhook.processed_at is not None

            assert intervention is not None
            assert intervention.status == InterventionStatus.SUCCEEDED
            assert intervention.provider_status == "paid"
            assert intervention.outcome is not None
            assert intervention.outcome.recovered is True
            assert intervention.outcome.recovered_amount == Decimal("100.00")
            assert intervention.decision.payment.status == PaymentStatus.RECOVERED
    finally:
        cleanup_test_data()


def test_already_processed_webhook_task_is_skipped():
    cleanup_test_data()

    try:
        webhook_id, intervention_id = seed_webhook(
            webhook_status="processed"
        )

        result = process_razorpay_webhook.run(webhook_id)

        assert result == {
            "status": "skipped",
            "webhook_event_id": webhook_id,
            "processing_status": "processed",
        }

        with SessionLocal() as db:
            intervention = db.get(Intervention, intervention_id)
            assert intervention is not None
            assert intervention.status == InterventionStatus.EXECUTED
            assert intervention.outcome is None
    finally:
        cleanup_test_data()


def test_failed_webhook_task_can_be_retried():
    cleanup_test_data()

    try:
        webhook_id, _ = seed_webhook(webhook_status="failed")

        result = process_razorpay_webhook.run(webhook_id)

        assert result["status"] == "processed"

        with SessionLocal() as db:
            webhook = db.get(WebhookEvent, webhook_id)
            assert webhook is not None
            assert webhook.status == "processed"
    finally:
        cleanup_test_data()


def test_missing_webhook_event_fails_clearly():
    cleanup_test_data()

    with pytest.raises(
        LookupError,
        match="WebhookEvent 999999999 was not found",
    ):
        process_razorpay_webhook.run(999999999)
