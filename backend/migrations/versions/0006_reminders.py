"""EMI and bill reminders, and the months marked paid

Revision ID: 0006_reminders
Revises: 0005_google_sign_in
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_reminders"
down_revision = "0005_google_sign_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.String(64), nullable=True),
        sa.Column("start_month", sa.String(7), nullable=False),
        sa.Column("total_months", sa.Integer(), nullable=True),
        sa.Column("remind_days_before", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("kind IN ('emi', 'bill')", name="ck_reminders_kind"),
    )
    op.create_index("ix_reminders_user_version", "reminders", ["user_id", "server_version"])

    op.create_table(
        "reminder_payments",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reminder_id", sa.String(64), primary_key=True),
        sa.Column("period_key", sa.String(7), primary_key=True),
        sa.Column("transaction_id", sa.String(64), nullable=True),
        sa.Column("created_expense", sa.Boolean(), nullable=False),
        sa.Column("paid_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_reminder_payments_user_version", "reminder_payments", ["user_id", "server_version"])


def downgrade() -> None:
    op.drop_index("ix_reminder_payments_user_version", table_name="reminder_payments")
    op.drop_table("reminder_payments")
    op.drop_index("ix_reminders_user_version", table_name="reminders")
    op.drop_table("reminders")
