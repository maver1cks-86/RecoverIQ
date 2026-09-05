from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.merchant import Merchant


class MerchantPolicy(Base):
    __tablename__ = "merchant_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchants.id"),
        unique=True,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    max_contacts: Mapped[int] = mapped_column(Integer, nullable=False)
    max_incentive: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    incentive_budget: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    minimum_margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    human_approval_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    merchant: Mapped[Merchant] = relationship(back_populates="policy")
