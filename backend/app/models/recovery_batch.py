from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.decision.actions import RecoveryAction
from app.models.enums import PolicyStatus
from sqlalchemy import Enum as SAEnum

if TYPE_CHECKING:
    from app.models.decision import RecoveryDecision
    from app.models.intervention import Intervention
    from app.models.merchant import Merchant
    from app.models.payment import Payment


class RecoveryBatch(Base):
    __tablename__ = "recovery_batches"
    __table_args__ = (Index("ix_recovery_batches_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="CREATED")
    payment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_at_risk: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    planning_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planning_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    merchant: Mapped[Merchant] = relationship()
    members: Mapped[list[RecoveryBatchPayment]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    plans: Mapped[list[OptimizationPlan]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class RecoveryBatchPayment(Base):
    __tablename__ = "recovery_batch_payments"
    __table_args__ = (UniqueConstraint("batch_id", "payment_id", name="uq_recovery_batch_payment"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recovery_batches.id", ondelete="CASCADE"), index=True, nullable=False)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    batch: Mapped[RecoveryBatch] = relationship(back_populates="members")
    payment: Mapped[Payment] = relationship()


class OptimizationPlan(Base):
    __tablename__ = "optimization_plans"
    __table_args__ = (
        UniqueConstraint("batch_id", "version", name="uq_optimization_plan_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recovery_batches.id", ondelete="CASCADE"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    solver_status: Mapped[str] = mapped_column(String(30), nullable=False)
    objective_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    expected_net_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    constraints_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_usage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    batch: Mapped[RecoveryBatch] = relationship(back_populates="plans")
    assignments: Mapped[list[OptimizationAssignment]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class OptimizationAssignment(Base):
    __tablename__ = "optimization_assignments"
    __table_args__ = (
        UniqueConstraint("plan_id", "payment_id", name="uq_optimization_assignment_payment"),
        Index("ix_optimization_assignments_plan_execution", "plan_id", "execution_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("optimization_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True, nullable=False)
    selected_action: Mapped[RecoveryAction] = mapped_column(SAEnum(RecoveryAction, name="recovery_action"), nullable=False)
    policy_status: Mapped[PolicyStatus] = mapped_column(SAEnum(PolicyStatus, name="policy_status"), nullable=False)
    recovery_probability: Mapped[float] = mapped_column(nullable=False)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    incremental_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    intervention_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    incentive_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="PLANNED")
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("recovery_decisions.id"))
    intervention_id: Mapped[int | None] = mapped_column(ForeignKey("interventions.id"))
    provider: Mapped[str | None] = mapped_column(String(50))
    provider_action_id: Mapped[str | None] = mapped_column(String(255), index=True)
    provider_status: Mapped[str | None] = mapped_column(String(100))
    payment_url: Mapped[str | None] = mapped_column(String(500))
    standalone_best_action: Mapped[str | None] = mapped_column(String(40))
    selected_rank: Mapped[int | None] = mapped_column(Integer)
    portfolio_agreement: Mapped[bool | None] = mapped_column()
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    policy_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[OptimizationPlan] = relationship(back_populates="assignments")
    payment: Mapped[Payment] = relationship()
    decision: Mapped[RecoveryDecision | None] = relationship()
    intervention: Mapped[Intervention | None] = relationship()
