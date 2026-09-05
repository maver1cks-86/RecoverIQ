import httpx
import pytest

from app.integrations.razorpay.client import (
    RazorpayAuthenticationError,
    RazorpayClient,
    RazorpayRateLimitError,
    RazorpayValidationError,
)
from app.integrations.razorpay.schemas import (
    CreatePaymentLinkRequest,
    RazorpayCustomer,
)


def build_client(handler):
    transport = httpx.MockTransport(handler)

    return RazorpayClient(
        key_id="rzp_test_fake",
        key_secret="fake_secret",
        base_url="https://api.razorpay.com/v1",
        transport=transport,
    )


@pytest.mark.asyncio
async def test_create_payment_link():
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert (
            request.url.path
            == "/v1/payment_links"
        )

        return httpx.Response(
            200,
            json={
                "id": "plink_test_123",
                "short_url": "https://rzp.io/i/test123",
                "status": "created",
                "amount": 250000,
                "amount_paid": 0,
                "currency": "INR",
                "reference_id": "recoveriq_test_001",
                "created_at": 1234567890,
                "expire_by": None,
            },
        )

    client = build_client(handler)

    result = await client.create_payment_link(
        CreatePaymentLinkRequest(
            amount=2500,
            reference_id="recoveriq_test_001",
            description="RecoverIQ recovery",
            customer=RazorpayCustomer(
                name="Test User",
                email="test@example.com",
                contact="+919999999999",
            ),
            notes={
                "source": "RecoverIQ",
                "recovery_action": "PAYMENT_LINK",
            },
        )
    )

    assert result.id == "plink_test_123"
    assert result.amount == 250000
    assert result.amount_paid == 0
    assert result.currency == "INR"
    assert result.status == "created"
    assert (
        result.reference_id
        == "recoveriq_test_001"
    )


@pytest.mark.asyncio
async def test_fetch_payment_link():
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert (
            request.url.path
            == "/v1/payment_links/plink_test_123"
        )

        return httpx.Response(
            200,
            json={
                "id": "plink_test_123",
                "short_url": "https://rzp.io/i/test123",
                "status": "created",
                "amount": 50000,
                "amount_paid": 0,
                "currency": "INR",
                "reference_id": "recoveriq_test_002",
                "created_at": 1234567890,
            },
        )

    client = build_client(handler)

    result = await client.fetch_payment_link(
        "plink_test_123"
    )

    assert result.id == "plink_test_123"
    assert result.status == "created"


@pytest.mark.asyncio
async def test_cancel_payment_link():
    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert (
            request.url.path
            == "/v1/payment_links/plink_test_123/cancel"
        )

        return httpx.Response(
            200,
            json={
                "id": "plink_test_123",
                "short_url": "https://rzp.io/i/test123",
                "status": "cancelled",
                "amount": 50000,
                "amount_paid": 0,
                "currency": "INR",
                "reference_id": "recoveriq_test_002",
                "created_at": 1234567890,
            },
        )

    client = build_client(handler)

    result = await client.cancel_payment_link(
        "plink_test_123"
    )

    assert result.status == "cancelled"


@pytest.mark.asyncio
async def test_authentication_error():
    def handler(request: httpx.Request):
        return httpx.Response(
            401,
            json={
                "error": {
                    "description": (
                        "Authentication failed"
                    )
                }
            },
        )

    client = build_client(handler)

    with pytest.raises(
        RazorpayAuthenticationError
    ) as exc_info:
        await client.fetch_payment_link(
            "plink_test_123"
        )

    assert exc_info.value.status_code == 401
    assert (
        str(exc_info.value)
        == "Authentication failed"
    )


@pytest.mark.asyncio
async def test_validation_error():
    def handler(request: httpx.Request):
        return httpx.Response(
            400,
            json={
                "error": {
                    "description": "Invalid amount"
                }
            },
        )

    client = build_client(handler)

    with pytest.raises(
        RazorpayValidationError
    ) as exc_info:
        await client.create_payment_link(
            CreatePaymentLinkRequest(
                amount=500,
                reference_id="recoveriq_test",
                description="Test",
            )
        )

    assert exc_info.value.status_code == 400
    assert str(exc_info.value) == "Invalid amount"


@pytest.mark.asyncio
async def test_rate_limit_error():
    def handler(request: httpx.Request):
        return httpx.Response(
            429,
            json={
                "error": {
                    "description": (
                        "Too many requests"
                    )
                }
            },
        )

    client = build_client(handler)

    with pytest.raises(
        RazorpayRateLimitError
    ):
        await client.fetch_payment_link(
            "plink_test_123"
        )


def test_missing_credentials():
    with pytest.raises(
        RazorpayAuthenticationError
    ):
        RazorpayClient(
            key_id="",
            key_secret="",
        )