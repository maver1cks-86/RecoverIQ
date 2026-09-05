from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import PaymentStatus

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.decision import RecoveryDecision
    from app.models.merchant import Merchant


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchants.id"),
        index=True,
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        index=True,
        nullable=False,
    )
    razorpay_payment_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"),
        index=True,
        nullable=False,
    )
    failure_code: Mapped[str | None] = mapped_column(
        String(100),
        index=True,
        nullable=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    merchant: Mapped[Merchant] = relationship(back_populates="payments")
    customer: Mapped[Customer] = relationship(back_populates="payments")
    recovery_decisions: Mapped[list[RecoveryDecision]] = relationship(
        back_populates="payment"
    )
