"""add durable recovery batches and optimizer assignments

Revision ID: a27c01b42f90
Revises: 7397f7def8ba
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a27c01b42f90"
down_revision: Union[str, Sequence[str], None] = "7397f7def8ba"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("recovery_batches", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchants.id"), nullable=False), sa.Column("source", sa.String(80), nullable=False), sa.Column("reference_id", sa.String(120), nullable=False, unique=True), sa.Column("status", sa.String(40), nullable=False), sa.Column("payment_count", sa.Integer(), nullable=False), sa.Column("revenue_at_risk", sa.Numeric(18,2), nullable=False), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("planning_started_at", sa.DateTime(timezone=True)), sa.Column("planning_completed_at", sa.DateTime(timezone=True)), sa.Column("execution_started_at", sa.DateTime(timezone=True)), sa.Column("execution_completed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_recovery_batches_reference_id", "recovery_batches", ["reference_id"], unique=True)
    op.create_index("ix_recovery_batches_merchant_id", "recovery_batches", ["merchant_id"]); op.create_index("ix_recovery_batches_status", "recovery_batches", ["status"]); op.create_index("ix_recovery_batches_status_created", "recovery_batches", ["status","created_at"])
    op.create_table("recovery_batch_payments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("recovery_batches.id", ondelete="CASCADE"), nullable=False), sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("batch_id","payment_id",name="uq_recovery_batch_payment"))
    op.create_index("ix_recovery_batch_payments_batch_id", "recovery_batch_payments", ["batch_id"]); op.create_index("ix_recovery_batch_payments_payment_id", "recovery_batch_payments", ["payment_id"])
    op.create_table("optimization_plans", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("recovery_batches.id", ondelete="CASCADE"), nullable=False), sa.Column("solver_status", sa.String(30), nullable=False), sa.Column("objective_value", sa.Numeric(18,2), nullable=False), sa.Column("expected_net_value", sa.Numeric(18,2), nullable=False), sa.Column("constraints_snapshot", postgresql.JSONB(), nullable=False), sa.Column("resource_usage", postgresql.JSONB(), nullable=False), sa.Column("model_version", sa.String(100), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_optimization_plans_batch_id", "optimization_plans", ["batch_id"])
    op.create_table("optimization_assignments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("plan_id", sa.Integer(), sa.ForeignKey("optimization_plans.id", ondelete="CASCADE"), nullable=False), sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False), sa.Column("selected_action", postgresql.ENUM(name="recovery_action", create_type=False), nullable=False), sa.Column("policy_status", postgresql.ENUM(name="policy_status", create_type=False), nullable=False), sa.Column("recovery_probability", sa.Float(), nullable=False), sa.Column("expected_value", sa.Numeric(18,2), nullable=False), sa.Column("incremental_value", sa.Numeric(18,2), nullable=False), sa.Column("intervention_cost", sa.Numeric(18,2), nullable=False), sa.Column("incentive_cost", sa.Numeric(18,2), nullable=False), sa.Column("execution_status", sa.String(40), nullable=False), sa.Column("decision_id", sa.Integer(), sa.ForeignKey("recovery_decisions.id")), sa.Column("intervention_id", sa.Integer(), sa.ForeignKey("interventions.id")), sa.Column("provider", sa.String(50)), sa.Column("provider_action_id", sa.String(255)), sa.Column("provider_status", sa.String(100)), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("executed_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("plan_id","payment_id",name="uq_optimization_assignment_payment"))
    for name, cols in [("ix_optimization_assignments_plan_id",["plan_id"]),("ix_optimization_assignments_payment_id",["payment_id"]),("ix_optimization_assignments_execution_status",["execution_status"]),("ix_optimization_assignments_provider_action_id",["provider_action_id"]),("ix_optimization_assignments_plan_execution",["plan_id","execution_status"])]: op.create_index(name,"optimization_assignments",cols)

def downgrade() -> None:
    op.drop_table("optimization_assignments"); op.drop_table("optimization_plans"); op.drop_table("recovery_batch_payments"); op.drop_table("recovery_batches")
