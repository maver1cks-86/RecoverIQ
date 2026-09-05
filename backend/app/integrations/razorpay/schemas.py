from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def rupees_to_paise(amount: float | Decimal) -> int:
    """
    Convert INR rupees to paise safely.

    Examples:
        2500 -> 250000
        100.50 -> 10050

    Raises ValueError when:
    - amount is invalid
    - amount is zero or negative
    - amount contains fractional paise
    """

    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(
            "Amount must be a valid number."
        ) from exc

    if value <= 0:
        raise ValueError(
            "Amount must be greater than zero."
        )

    paise = value * Decimal("100")

    if paise != paise.to_integral_value():
        raise ValueError(
            "Amount cannot contain fractional paise."
        )

    return int(paise)


@dataclass(frozen=True)
class RazorpayCustomer:
    name: str | None = None
    email: str | None = None
    contact: str | None = None


@dataclass(frozen=True)
class CreatePaymentLinkRequest:
    amount: float | Decimal
    reference_id: str
    description: str

    customer: RazorpayCustomer | None = None

    currency: str = "INR"

    notify_sms: bool = False
    notify_email: bool = False

    notes: dict[str, str] | None = None


@dataclass(frozen=True)
class PaymentLinkResult:
    id: str
    short_url: str | None
    status: str

    amount: int
    amount_paid: int

    currency: str
    reference_id: str | None

    created_at: int | None
    expire_by: int | None