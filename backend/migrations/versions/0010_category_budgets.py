"""monthly budget per category

Revision ID: 0010_category_budgets
Revises: 0009_reminder_times
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_category_budgets"
down_revision = "0009_reminder_times"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.add_column(sa.Column("budget_minor", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch:
        batch.drop_column("budget_minor")
