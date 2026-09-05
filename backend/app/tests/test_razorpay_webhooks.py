import hashlib
import hmac
import json

import pytest

from app.integrations.razorpay.webhooks import (
    RazorpayWebhookPayloadError,
    RazorpayWebhookSignatureError,
    parse_webhook_event,
    verify_webhook_signature,
)


WEBHOOK_SECRET = "recoveriq_test_webhook_secret"


def make_signature(
    body: bytes,
) -> str:
    return hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


def test_valid_webhook_signature():
    body = b'{"event":"payment_link.paid"}'

    signature = make_signature(body)

    verify_webhook_signature(
        raw_body=body,
        received_signature=signature,
        webhook_secret=WEBHOOK_SECRET,
    )


def test_invalid_webhook_signature():
    body = b'{"event":"payment_link.paid"}'

    with pytest.raises(
        RazorpayWebhookSignatureError
    ):
        verify_webhook_signature(
            raw_body=body,
            received_signature="invalid",
            webhook_secret=WEBHOOK_SECRET,
        )


def test_missing_signature():
    body = b'{"event":"payment_link.paid"}'

    with pytest.raises(
        RazorpayWebhookSignatureError
    ):
        verify_webhook_signature(
            raw_body=body,
            received_signature="",
            webhook_secret=WEBHOOK_SECRET,
        )


def test_missing_webhook_secret():
    body = b'{"event":"payment_link.paid"}'

    with pytest.raises(
        RazorpayWebhookSignatureError
    ):
        verify_webhook_signature(
            raw_body=body,
            received_signature="abc",
            webhook_secret="",
        )


def test_parse_payment_link_event():
    body = json.dumps(
        {
            "entity": "event",
            "account_id": "acc_test_123",
            "event": "payment_link.paid",
            "created_at": 1720000000,
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": "plink_test_123",
                        "status": "paid",
                        "amount": 1000,
                        "amount_paid": 1000,
                        "currency": "INR",
                    }
                }
            },
        }
    ).encode("utf-8")

    result = parse_webhook_event(
        raw_body=body,
        event_id="event_test_001",
    )

    assert result.event_id == "event_test_001"
    assert (
        result.event_type
        == "payment_link.paid"
    )
    assert result.account_id == "acc_test_123"
    assert result.created_at == 1720000000

    payment_link = result.payload[
        "payment_link"
    ]["entity"]

    assert payment_link["id"] == "plink_test_123"
    assert payment_link["status"] == "paid"


def test_parse_rejects_invalid_json():
    with pytest.raises(
        RazorpayWebhookPayloadError
    ):
        parse_webhook_event(
            raw_body=b"not-json",
            event_id="event_test_001",
        )


def test_parse_requires_event_id():
    body = json.dumps(
        {
            "event": "payment_link.paid",
            "payload": {},
        }
    ).encode("utf-8")

    with pytest.raises(
        RazorpayWebhookPayloadError
    ):
        parse_webhook_event(
            raw_body=body,
            event_id="",
        )


def test_parse_requires_event_type():
    body = json.dumps(
        {
            "payload": {},
        }
    ).encode("utf-8")

    with pytest.raises(
        RazorpayWebhookPayloadError
    ):
        parse_webhook_event(
            raw_body=body,
            event_id="event_test_001",
        )


def test_signature_uses_exact_raw_body():
    body_1 = (
        b'{"event":"payment_link.paid",'
        b'"payload":{}}'
    )

    body_2 = (
        b'{ "event": "payment_link.paid", '
        b'"payload": {} }'
    )

    signature = make_signature(body_1)

    verify_webhook_signature(
        raw_body=body_1,
        received_signature=signature,
        webhook_secret=WEBHOOK_SECRET,
    )

    with pytest.raises(
        RazorpayWebhookSignatureError
    ):
        verify_webhook_signature(
            raw_body=body_2,
            received_signature=signature,
            webhook_secret=WEBHOOK_SECRET,
        )