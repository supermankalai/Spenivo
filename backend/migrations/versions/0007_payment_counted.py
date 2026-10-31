"""whether a paid EMI/bill counts in the monthly budget

Revision ID: 0007_payment_counted
Revises: 0006_reminders
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_payment_counted"
down_revision = "0006_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reminder_payments") as batch:
        batch.add_column(sa.Column("counted", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("reminder_payments") as batch:
        batch.drop_column("counted")
