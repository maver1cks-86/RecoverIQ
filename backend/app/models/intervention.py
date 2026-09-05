from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.decision.actions import RecoveryAction
from app.models.enums import InterventionStatus

if TYPE_CHECKING:
    from app.models.decision import RecoveryDecision
    from app.models.outcome import Outcome


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(primary_key=True)

    decision_id: Mapped[int] = mapped_column(
        ForeignKey("recovery_decisions.id"),
        index=True,
        nullable=False,
    )

    action_type: Mapped[RecoveryAction] = mapped_column(
        SAEnum(RecoveryAction, name="recovery_action"),
        nullable=False,
    )

    status: Mapped[InterventionStatus] = mapped_column(
        SAEnum(InterventionStatus, name="intervention_status"),
        nullable=False,
    )

    # External payment/recovery provider, e.g. "razorpay".
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # Provider-side identifier for the executed recovery action.
    # For PAYMENT_LINK this will contain the Razorpay plink_* ID.
    provider_action_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
        nullable=True,
    )

    # Raw provider status, e.g. created, paid, cancelled, expired.
    provider_status: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Timestamp of the newest provider event applied to this intervention.
    # Used to protect against out-of-order webhook delivery.
    last_provider_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    intervention_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        server_default=text("0"),
        nullable=False,
    )

    incentive_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        server_default=text("0"),
        nullable=False,
    )

    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    decision: Mapped[RecoveryDecision] = relationship(
        back_populates="interventions"
    )

    outcome: Mapped[Outcome | None] = relationship(
        back_populates="intervention",
        uselist=False,
    )