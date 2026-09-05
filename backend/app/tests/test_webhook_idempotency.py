from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.config import settings
from app.database import SessionLocal
from app.decision.actions import RecoveryAction
from app.main import app
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


client = TestClient(app)

TEST_SECRET = "recoveriq_idempotency_test_secret"
TEST_EVENT_ID = "event_idempotency_001"
TEST_PAYMENT_LINK_ID = "plink_test_001"


def _signature(raw_body: bytes) -> str:
    return hmac.new(
        TEST_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


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
            name="Webhook Idempotency Test Merchant",
        )
        db.add(merchant)
        db.flush()

        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id="cust_idempotency_test_001",
        )
        db.add(customer)
        db.flush()

        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            razorpay_payment_id="pay_idempotency_original",
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
        db.commit()

        return intervention.id, payment.id


def test_duplicate_razorpay_webhook_is_stored_once():
    old_secret = settings.RAZORPAY_WEBHOOK_SECRET
    settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET

    _cleanup()

    try:
        intervention_id, payment_id = _seed_intervention()

        payload = {
            "entity": "event",
            "account_id": "acc_test",
            "event": "payment_link.paid",
            "created_at": 1788280000,
            "payload": {
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
        }

        raw_body = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": _signature(raw_body),
            "X-Razorpay-Event-Id": TEST_EVENT_ID,
        }

        with patch(
            "app.api.webhooks.process_razorpay_webhook.delay"
        ) as delay_mock:
            first_response = client.post(
                "/webhooks/razorpay",
                content=raw_body,
                headers=headers,
            )

            with SessionLocal() as db:
                stored_event = db.scalar(
                    select(WebhookEvent).where(
                        WebhookEvent.provider == "razorpay",
                        WebhookEvent.provider_event_id == TEST_EVENT_ID,
                    )
                )
                assert stored_event is not None
                webhook_event_id = stored_event.id

            process_razorpay_webhook.run(webhook_event_id)

            second_response = client.post(
                "/webhooks/razorpay",
                content=raw_body,
                headers=headers,
            )

            delay_mock.assert_called_once_with(webhook_event_id)

        assert first_response.status_code == 200
        assert second_response.status_code == 200

        first_data = first_response.json()
        second_data = second_response.json()

        assert first_data["status"] == "queued"
        assert first_data["event_id"] == TEST_EVENT_ID
        assert first_data["event_type"] == "payment_link.paid"

        assert second_data["status"] == "duplicate"
        assert second_data["event_id"] == TEST_EVENT_ID
        assert second_data["event_type"] == "payment_link.paid"
        assert second_data["processing_status"] == "processed"

        with SessionLocal() as db:
            events = db.scalars(
                select(WebhookEvent).where(
                    WebhookEvent.provider == "razorpay",
                    WebhookEvent.provider_event_id == TEST_EVENT_ID,
                )
            ).all()

            assert len(events) == 1

            webhook = events[0]

            assert webhook.status == "processed"
            assert webhook.processed_at is not None

            intervention = db.get(
                Intervention,
                intervention_id,
            )

            payment = db.get(
                Payment,
                payment_id,
            )

            assert intervention is not None
            assert intervention.status == InterventionStatus.SUCCEEDED
            assert intervention.provider_status == "paid"

            assert intervention.outcome is not None
            assert intervention.outcome.recovered is True
            assert (
                intervention.outcome.recovered_amount
                == Decimal("100.00")
            )

            assert payment is not None
            assert payment.status == PaymentStatus.RECOVERED

    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = old_secret
        _cleanup()
