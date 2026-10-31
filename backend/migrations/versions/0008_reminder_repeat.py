"""reminders a day and the snooze button for EMIs/bills

Revision ID: 0008_reminder_repeat
Revises: 0007_payment_counted
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_reminder_repeat"
down_revision = "0007_payment_counted"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.add_column(sa.Column("times_per_day", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("snooze", sa.String(8), nullable=False, server_default="1h"))


def downgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("snooze")
        batch.drop_column("times_per_day")
