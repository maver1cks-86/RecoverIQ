import pytest

from app.integrations.razorpay.schemas import (
    PaymentLinkResult,
)
from app.services.recovery_service import (
    RecoveryService,
)


class FakeRazorpayClient:
    def __init__(self):
        self.last_request = None

    async def create_payment_link(
        self,
        request,
    ):
        self.last_request = request

        return PaymentLinkResult(
            id="plink_test_001",
            short_url="https://rzp.io/i/test001",
            status="created",
            amount=250000,
            amount_paid=0,
            currency="INR",
            reference_id=request.reference_id,
            created_at=1234567890,
            expire_by=None,
        )


@pytest.mark.asyncio
async def test_execute_payment_link():
    fake_client = FakeRazorpayClient()

    service = RecoveryService(
        razorpay_client=fake_client
    )

    result = await service.execute_payment_link(
        original_payment_id="pay_123",
        amount=2500,
        customer_name="Test User",
        customer_email="test@example.com",
        customer_phone="+919999999999",
    )

    assert result.provider == "razorpay"
    assert result.action == "PAYMENT_LINK"
    assert result.success is True
    assert result.provider_action_id == "plink_test_001"
    assert result.payment_url == "https://rzp.io/i/test001"
    assert result.status == "created"

    request = fake_client.last_request

    assert request is not None
    assert request.amount == 2500
    assert request.notify_sms is False
    assert request.notify_email is False

    assert request.customer is not None
    assert request.customer.name == "Test User"
    assert request.customer.email == "test@example.com"
    assert request.customer.contact == "+919999999999"

    assert request.notes["source"] == "RecoverIQ"
    assert (
        request.notes["recovery_action"]
        == "PAYMENT_LINK"
    )
    assert (
        request.notes["original_payment_id"]
        == "pay_123"
    )

    assert request.reference_id.startswith(
    "ri_pay_123_"
)

    assert len(request.reference_id) <= 40


@pytest.mark.asyncio
async def test_execute_payment_link_without_customer():
    fake_client = FakeRazorpayClient()

    service = RecoveryService(
        razorpay_client=fake_client
    )

    result = await service.execute_payment_link(
        original_payment_id="pay_456",
        amount=500,
    )

    assert result.success is True
    assert fake_client.last_request.customer is None


@pytest.mark.asyncio
async def test_execute_payment_link_rejects_empty_payment_id():
    fake_client = FakeRazorpayClient()

    service = RecoveryService(
        razorpay_client=fake_client
    )

    with pytest.raises(ValueError):
        await service.execute_payment_link(
            original_payment_id="   ",
            amount=500,
        )
def test_reference_id_never_exceeds_40_characters():
    reference_id = RecoveryService._build_reference_id(
        "pay_this_is_an_extremely_long_original_payment_identifier_123456789"
    )

    assert len(reference_id) <= 40
    assert reference_id.startswith("ri_")


def test_reference_id_is_stable_for_assignment_retry():
    first = RecoveryService._build_reference_id(
        "pay_123", idempotency_key="optimization-assignment-42"
    )
    second = RecoveryService._build_reference_id(
        "pay_123", idempotency_key="optimization-assignment-42"
    )
    assert first == second
