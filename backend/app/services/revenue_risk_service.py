from decimal import Decimal

from app.models.enums import PaymentStatus
from app.models.payment import Payment


class RevenueRiskService:
    """Deterministic classification for the current failed-payment scope."""

    @staticmethod
    def is_at_risk(payment: Payment) -> bool:
        return payment.status is PaymentStatus.FAILED and payment.amount > Decimal("0")

    @classmethod
    def amount_at_risk(cls, payment: Payment) -> Decimal:
        return payment.amount if cls.is_at_risk(payment) else Decimal("0.00")

    @classmethod
    def require_at_risk(cls, payment: Payment) -> None:
        if not cls.is_at_risk(payment):
            raise ValueError(f"Payment {payment.id} is not an eligible FAILED revenue-at-risk payment.")
