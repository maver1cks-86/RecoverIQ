"""version optimization plans and persist policy evidence

Revision ID: d304planversion
Revises: c275evidence01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d304planversion"
down_revision: Union[str, Sequence[str], None] = "c275evidence01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "optimization_plans",
        sa.Column("version", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY batch_id ORDER BY created_at, id
            ) AS plan_version
            FROM optimization_plans
        )
        UPDATE optimization_plans AS plans
        SET version = numbered.plan_version
        FROM numbered
        WHERE plans.id = numbered.id
        """
    )
    op.alter_column(
        "optimization_plans",
        "version",
        nullable=False,
        server_default="1",
    )
    op.create_unique_constraint(
        "uq_optimization_plan_version",
        "optimization_plans",
        ["batch_id", "version"],
    )
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "policy_evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("optimization_assignments", "policy_evidence")
    op.drop_constraint(
        "uq_optimization_plan_version",
        "optimization_plans",
        type_="unique",
    )
    op.drop_column("optimization_plans", "version")
