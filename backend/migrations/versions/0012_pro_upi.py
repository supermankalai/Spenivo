"""Pro by UPI: users.pro_until and pro_payments

Revision ID: 0012_pro_upi
Revises: 0011_splits
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_pro_upi"
down_revision = "0011_splits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("pro_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "pro_payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(12), nullable=False, unique=True),
        sa.Column("plan", sa.String(8), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("utr", sa.String(22), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'claimed', 'approved', 'rejected')", name="ck_pro_payments_status"),
        sa.CheckConstraint("plan IN ('monthly', 'yearly')", name="ck_pro_payments_plan"),
    )
    op.create_index("ix_pro_payments_user_id", "pro_payments", ["user_id"])
    op.create_index("ix_pro_payments_utr", "pro_payments", ["utr"])


def downgrade() -> None:
    op.drop_index("ix_pro_payments_utr", table_name="pro_payments")
    op.drop_index("ix_pro_payments_user_id", table_name="pro_payments")
    op.drop_table("pro_payments")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("pro_until")
