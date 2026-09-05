from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from app.integrations.razorpay.client import RazorpayClient
from app.integrations.razorpay.schemas import (
    CreatePaymentLinkRequest,
    RazorpayCustomer,
)


@dataclass(frozen=True)
class RecoveryExecutionResult:
    provider: str
    action: str
    success: bool
    provider_action_id: str | None
    payment_url: str | None
    status: str | None
    reference_id: str | None


class RecoveryService:
    """
    Executes approved recovery actions.

    Phase 19 supports PAYMENT_LINK only.
    """

    def __init__(
        self,
        razorpay_client: RazorpayClient | None = None,
    ):
        self.razorpay_client = (
            razorpay_client
            if razorpay_client is not None
            else RazorpayClient()
        )

    async def execute_payment_link(
        self,
        *,
        original_payment_id: str,
        amount: float,
        customer_name: str | None = None,
        customer_email: str | None = None,
        customer_phone: str | None = None,
        idempotency_key: str | None = None,
    ) -> RecoveryExecutionResult:
        if not original_payment_id.strip():
            raise ValueError(
                "original_payment_id is required."
            )

        reference_id = self._build_reference_id(
            original_payment_id,
            idempotency_key=idempotency_key,
        )

        customer = None

        if any(
            [
                customer_name,
                customer_email,
                customer_phone,
            ]
        ):
            customer = RazorpayCustomer(
                name=customer_name,
                email=customer_email,
                contact=customer_phone,
            )

        request = CreatePaymentLinkRequest(
            amount=amount,
            reference_id=reference_id,
            description="RecoverIQ payment recovery",
            customer=customer,
            notify_sms=False,
            notify_email=False,
            notes={
                "source": "RecoverIQ",
                "recovery_action": "PAYMENT_LINK",
                "original_payment_id": original_payment_id,
            },
        )

        result = await self.razorpay_client.create_payment_link(
            request
        )

        return RecoveryExecutionResult(
            provider="razorpay",
            action="PAYMENT_LINK",
            success=True,
            provider_action_id=result.id,
            payment_url=result.short_url,
            status=result.status,
            reference_id=result.reference_id,
        )


    @staticmethod
    def _build_reference_id(
        original_payment_id: str,
        idempotency_key: str | None = None,
    ) -> str:
        safe_payment_id = (
            original_payment_id
            .strip()
            .replace(" ", "_")
        )

        stable_key = idempotency_key or original_payment_id
        suffix = sha256(stable_key.encode("utf-8")).hexdigest()[:10]

        prefix = "ri_"

        max_payment_id_length = (
            40
            - len(prefix)
            - 1
            - len(suffix)
        )

        safe_payment_id = safe_payment_id[
            :max_payment_id_length
        ]

        reference_id = (
            f"{prefix}"
            f"{safe_payment_id}_"
            f"{suffix}"
        )

        return reference_id
