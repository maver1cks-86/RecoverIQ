from __future__ import annotations

import hashlib
import hmac
import json
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


client = TestClient(app)

TEST_SECRET = "recoveriq_endpoint_test_secret"
TEST_PAYMENT_LINK_ID = "plink_test_123"


def sign(body: bytes) -> str:
    return hmac.new(
        TEST_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def build_event() -> bytes:
    return json.dumps(
        {
            "entity": "event",
            "account_id": "acc_test_123",
            "event": "payment_link.paid",
            "created_at": 1720000000,
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": TEST_PAYMENT_LINK_ID,
                        "status": "paid",
                        "amount": 1000,
                        "amount_paid": 1000,
                        "currency": "INR",
                    }
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


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


def seed_payment_link_intervention() -> None:
    with SessionLocal() as db:
        merchant = Merchant(
            name="Webhook Endpoint Test Merchant",
        )
        db.add(merchant)
        db.flush()

        customer = Customer(
            merchant_id=merchant.id,
            external_customer_id="cust_endpoint_test_001",
        )
        db.add(customer)
        db.flush()

        payment = Payment(
            merchant_id=merchant.id,
            customer_id=customer.id,
            razorpay_payment_id="pay_endpoint_original",
            amount=Decimal("10.00"),
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
            expected_value=Decimal("6.50"),
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


def test_valid_razorpay_webhook():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET

    cleanup_test_data()

    try:
        settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET

        seed_payment_link_intervention()

        body = build_event()

        with patch(
            "app.api.webhooks.process_razorpay_webhook.delay"
        ) as delay_mock:
            response = client.post(
                "/webhooks/razorpay",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": sign(body),
                    "X-Razorpay-Event-Id": "event_test_001",
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "queued"
        assert data["event_id"] == "event_test_001"
        assert data["event_type"] == "payment_link.paid"

        with SessionLocal() as db:
            webhook = db.query(WebhookEvent).filter(
                WebhookEvent.provider == "razorpay",
                WebhookEvent.provider_event_id == "event_test_001",
            ).one()

            intervention = db.query(Intervention).filter(
                Intervention.provider == "razorpay",
                Intervention.provider_action_id == TEST_PAYMENT_LINK_ID,
            ).one()

            payment = intervention.decision.payment

            delay_mock.assert_called_once_with(webhook.id)

            assert webhook.status == "received"
            assert webhook.processed_at is None

            assert intervention.status == InterventionStatus.EXECUTED
            assert intervention.provider_status == "created"

            assert intervention.outcome is None

            assert payment.status == PaymentStatus.FAILED

    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret
        cleanup_test_data()


def test_webhook_rejects_invalid_signature():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET

    try:
        settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET

        body = build_event()

        response = client.post(
            "/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "invalid",
                "X-Razorpay-Event-Id": "event_test_001",
            },
        )

        assert response.status_code == 401

    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret


def test_webhook_rejects_missing_event_id():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET

    try:
        settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET

        body = build_event()

        response = client.post(
            "/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sign(body),
            },
        )

        assert response.status_code == 400

    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret


def test_webhook_rejects_modified_body():
    original_secret = settings.RAZORPAY_WEBHOOK_SECRET

    try:
        settings.RAZORPAY_WEBHOOK_SECRET = TEST_SECRET

        original_body = build_event()
        signature = sign(original_body)

        modified_body = original_body.replace(
            b'"paid"',
            b'"created"',
        )

        response = client.post(
            "/webhooks/razorpay",
            content=modified_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": "event_test_001",
            },
        )

        assert response.status_code == 401

    finally:
        settings.RAZORPAY_WEBHOOK_SECRET = original_secret
