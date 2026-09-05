from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.payment import Payment
    from app.models.policy import MerchantPolicy


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    customers: Mapped[list[Customer]] = relationship(back_populates="merchant")
    payments: Mapped[list[Payment]] = relationship(back_populates="merchant")
    policy: Mapped[MerchantPolicy | None] = relationship(
        back_populates="merchant",
        uselist=False,
    )
