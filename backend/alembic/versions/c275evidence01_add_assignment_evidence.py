"""persist batch assignment evidence and payment links

Revision ID: c275evidence01
Revises: a27c01b42f90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c275evidence01"
down_revision: Union[str, Sequence[str], None] = "a27c01b42f90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("optimization_assignments", sa.Column("payment_url", sa.String(500)))
    op.add_column("optimization_assignments", sa.Column("standalone_best_action", sa.String(40)))
    op.add_column("optimization_assignments", sa.Column("selected_rank", sa.Integer()))
    op.add_column("optimization_assignments", sa.Column("portfolio_agreement", sa.Boolean()))
    op.add_column(
        "optimization_assignments",
        sa.Column(
            "alternatives",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("optimization_assignments", "alternatives")
    op.drop_column("optimization_assignments", "portfolio_agreement")
    op.drop_column("optimization_assignments", "selected_rank")
    op.drop_column("optimization_assignments", "standalone_best_action")
    op.drop_column("optimization_assignments", "payment_url")
