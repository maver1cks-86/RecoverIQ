from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.decision.actions import RecoveryAction
from app.models.enums import PolicyStatus

if TYPE_CHECKING:
    from app.models.intervention import Intervention
    from app.models.payment import Payment


class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id"),
        index=True,
        nullable=False,
    )
    selected_action: Mapped[RecoveryAction] = mapped_column(
        SAEnum(RecoveryAction, name="recovery_action"),
        nullable=False,
    )
    predicted_probability: Mapped[float] = mapped_column(Float, nullable=False)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    policy_status: Mapped[PolicyStatus] = mapped_column(
        SAEnum(PolicyStatus, name="policy_status"),
        nullable=False,
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    payment: Mapped[Payment] = relationship(back_populates="recovery_decisions")
    interventions: Mapped[list[Intervention]] = relationship(
        back_populates="decision"
    )
