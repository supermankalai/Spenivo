"""custom reminder times for EMIs/bills

Revision ID: 0009_reminder_times
Revises: 0008_reminder_repeat
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_reminder_times"
down_revision = "0008_reminder_repeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.add_column(sa.Column("remind_times", sa.String(32), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("remind_times")
