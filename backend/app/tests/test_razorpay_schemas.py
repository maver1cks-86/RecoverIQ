from decimal import Decimal

import pytest

from app.integrations.razorpay.schemas import (
    CreatePaymentLinkRequest,
    RazorpayCustomer,
    rupees_to_paise,
)


def test_rupees_to_paise_whole_number():
    assert rupees_to_paise(2500) == 250000


def test_rupees_to_paise_decimal():
    assert rupees_to_paise(100.50) == 10050


def test_rupees_to_paise_decimal_object():
    assert rupees_to_paise(
        Decimal("123.45")
    ) == 12345


def test_rupees_to_paise_rejects_zero():
    with pytest.raises(ValueError):
        rupees_to_paise(0)


def test_rupees_to_paise_rejects_negative():
    with pytest.raises(ValueError):
        rupees_to_paise(-100)


def test_rupees_to_paise_rejects_fractional_paise():
    with pytest.raises(ValueError):
        rupees_to_paise(10.005)


def test_razorpay_customer_schema():
    customer = RazorpayCustomer(
        name="Test User",
        email="test@example.com",
        contact="+919999999999",
    )

    assert customer.name == "Test User"
    assert customer.email == "test@example.com"
    assert customer.contact == "+919999999999"


def test_create_payment_link_request_defaults():
    request = CreatePaymentLinkRequest(
        amount=500,
        reference_id="recoveriq_test_001",
        description="RecoverIQ test payment",
    )

    assert request.currency == "INR"
    assert request.notify_sms is False
    assert request.notify_email is False
    assert request.customer is None
    assert request.notes is None