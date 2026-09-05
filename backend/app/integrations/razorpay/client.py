from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.integrations.razorpay.schemas import (
    CreatePaymentLinkRequest,
    PaymentLinkResult,
    rupees_to_paise,
)


class RazorpayIntegrationError(Exception):
    """Base exception for Razorpay integration failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code


class RazorpayAuthenticationError(RazorpayIntegrationError):
    """Raised when Razorpay rejects authentication."""


class RazorpayValidationError(RazorpayIntegrationError):
    """Raised when Razorpay rejects request data."""


class RazorpayRateLimitError(RazorpayIntegrationError):
    """Raised when Razorpay rate-limits the request."""


class RazorpayClient:
    """
    Minimal async Razorpay HTTP adapter.

    External Razorpay-specific HTTP behavior should stay
    inside this class rather than leaking into RecoverIQ's
    decision or execution layers.
    """

    def __init__(
        self,
        *,
        key_id: str | None = None,
        key_secret: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.key_id = (
            key_id
            if key_id is not None
            else settings.RAZORPAY_KEY_ID
        )

        self.key_secret = (
            key_secret
            if key_secret is not None
            else settings.RAZORPAY_KEY_SECRET
        )

        self.base_url = (
            base_url
            if base_url is not None
            else settings.RAZORPAY_BASE_URL
        ).rstrip("/")

        self.timeout_seconds = timeout_seconds
        self.transport = transport

        if not self.key_id or not self.key_secret:
            raise RazorpayAuthenticationError(
                "Razorpay credentials are not configured."
            )

    async def create_payment_link(
        self,
        request: CreatePaymentLinkRequest,
    ) -> PaymentLinkResult:
        payload = self._build_payment_link_payload(request)

        response = await self._request(
            method="POST",
            path="/payment_links",
            json=payload,
        )

        return self._parse_payment_link(response)

    async def fetch_payment_link(
        self,
        payment_link_id: str,
    ) -> PaymentLinkResult:
        if not payment_link_id:
            raise RazorpayValidationError(
                "Payment Link ID is required."
            )

        response = await self._request(
            method="GET",
            path=f"/payment_links/{payment_link_id}",
        )

        return self._parse_payment_link(response)

    async def cancel_payment_link(
        self,
        payment_link_id: str,
    ) -> PaymentLinkResult:
        if not payment_link_id:
            raise RazorpayValidationError(
                "Payment Link ID is required."
            )

        response = await self._request(
            method="POST",
            path=f"/payment_links/{payment_link_id}/cancel",
        )

        return self._parse_payment_link(response)

    def _build_payment_link_payload(
        self,
        request: CreatePaymentLinkRequest,
    ) -> dict[str, Any]:
        if not request.reference_id.strip():
            raise RazorpayValidationError(
                "reference_id is required."
            )

        if not request.description.strip():
            raise RazorpayValidationError(
                "description is required."
            )

        payload: dict[str, Any] = {
            "amount": rupees_to_paise(request.amount),
            "currency": request.currency,
            "reference_id": request.reference_id,
            "description": request.description,
            "notify": {
                "sms": request.notify_sms,
                "email": request.notify_email,
            },
        }

        if request.customer is not None:
            customer: dict[str, str] = {}

            if request.customer.name:
                customer["name"] = request.customer.name

            if request.customer.email:
                customer["email"] = request.customer.email

            if request.customer.contact:
                customer["contact"] = request.customer.contact

            if customer:
                payload["customer"] = customer

        if request.notes:
            payload["notes"] = request.notes

        return payload

    async def _request(
        self,
        *,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                auth=(
                    self.key_id,
                    self.key_secret,
                ),
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method=method,
                    url=path,
                    json=json,
                )

        except httpx.TimeoutException as exc:
            raise RazorpayIntegrationError(
                "Razorpay request timed out."
            ) from exc

        except httpx.RequestError as exc:
            raise RazorpayIntegrationError(
                "Could not communicate with Razorpay."
            ) from exc

        if response.is_success:
            try:
                data = response.json()
            except ValueError as exc:
                raise RazorpayIntegrationError(
                    "Razorpay returned an invalid JSON response.",
                    status_code=response.status_code,
                ) from exc

            if not isinstance(data, dict):
                raise RazorpayIntegrationError(
                    "Razorpay returned an unexpected response.",
                    status_code=response.status_code,
                )

            return data

        message = self._extract_error_message(response)

        if response.status_code in (401, 403):
            raise RazorpayAuthenticationError(
                message,
                status_code=response.status_code,
            )

        if response.status_code == 429:
            raise RazorpayRateLimitError(
                message,
                status_code=response.status_code,
            )

        if 400 <= response.status_code < 500:
            raise RazorpayValidationError(
                message,
                status_code=response.status_code,
            )

        raise RazorpayIntegrationError(
            message,
            status_code=response.status_code,
        )

    @staticmethod
    def _extract_error_message(
        response: httpx.Response,
    ) -> str:
        default_message = (
            f"Razorpay request failed with "
            f"HTTP {response.status_code}."
        )

        try:
            data = response.json()
        except ValueError:
            return default_message

        if not isinstance(data, dict):
            return default_message

        error = data.get("error")

        if isinstance(error, dict):
            description = error.get("description")

            if isinstance(description, str) and description:
                return description

        return default_message

    @staticmethod
    def _parse_payment_link(
        data: dict[str, Any],
    ) -> PaymentLinkResult:
        try:
            return PaymentLinkResult(
                id=str(data["id"]),
                short_url=data.get("short_url"),
                status=str(data["status"]),
                amount=int(data["amount"]),
                amount_paid=int(
                    data.get("amount_paid", 0)
                ),
                currency=str(data["currency"]),
                reference_id=data.get("reference_id"),
                created_at=data.get("created_at"),
                expire_by=data.get("expire_by"),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise RazorpayIntegrationError(
                "Razorpay Payment Link response "
                "was missing required fields."
            ) from exc