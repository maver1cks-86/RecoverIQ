from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


class RazorpayWebhookError(Exception):
    """Base exception for Razorpay webhook failures."""


class RazorpayWebhookSignatureError(
    RazorpayWebhookError
):
    """Raised when webhook signature verification fails."""


class RazorpayWebhookPayloadError(
    RazorpayWebhookError
):
    """Raised when webhook payload is malformed."""


@dataclass(frozen=True)
class RazorpayWebhookEvent:
    event_id: str
    event_type: str
    account_id: str | None
    created_at: int | None
    payload: dict[str, Any]


def verify_webhook_signature(
    *,
    raw_body: bytes,
    received_signature: str,
    webhook_secret: str,
) -> None:
    """
    Verify Razorpay webhook HMAC-SHA256 signature.

    IMPORTANT:
    raw_body must be the exact request body bytes received
    from Razorpay before JSON parsing.
    """

    if not webhook_secret:
        raise RazorpayWebhookSignatureError(
            "Razorpay webhook secret is not configured."
        )

    if not received_signature:
        raise RazorpayWebhookSignatureError(
            "Missing X-Razorpay-Signature header."
        )

    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected_signature,
        received_signature,
    ):
        raise RazorpayWebhookSignatureError(
            "Invalid Razorpay webhook signature."
        )


def parse_webhook_event(
    *,
    raw_body: bytes,
    event_id: str,
) -> RazorpayWebhookEvent:
    if not event_id:
        raise RazorpayWebhookPayloadError(
            "Missing X-Razorpay-Event-Id header."
        )

    try:
        data = json.loads(raw_body)
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise RazorpayWebhookPayloadError(
            "Webhook body is not valid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise RazorpayWebhookPayloadError(
            "Webhook payload must be a JSON object."
        )

    event_type = data.get("event")

    if not isinstance(event_type, str):
        raise RazorpayWebhookPayloadError(
            "Webhook event type is missing."
        )

    payload = data.get("payload")

    if not isinstance(payload, dict):
        raise RazorpayWebhookPayloadError(
            "Webhook payload field is missing."
        )

    created_at = data.get("created_at")

    if created_at is not None:
        try:
            created_at = int(created_at)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise RazorpayWebhookPayloadError(
                "Webhook created_at is invalid."
            ) from exc

    account_id = data.get("account_id")

    if (
        account_id is not None
        and not isinstance(account_id, str)
    ):
        raise RazorpayWebhookPayloadError(
            "Webhook account_id is invalid."
        )

    return RazorpayWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        account_id=account_id,
        created_at=created_at,
        payload=payload,
    )