"""split expenses: who owes the user

Revision ID: 0011_splits
Revises: 0010_category_budgets
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_splits"
down_revision = "0010_category_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "splits",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("person", sa.String(40), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("settled_at", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_splits_user_version", "splits", ["user_id", "server_version"])


def downgrade() -> None:
    op.drop_index("ix_splits_user_version", table_name="splits")
    op.drop_table("splits")
