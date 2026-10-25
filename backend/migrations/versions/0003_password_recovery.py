"""password recovery codes and sign-out on password change

Revision ID: 0003_password_recovery
Revises: 0002_username
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_password_recovery"
down_revision = "0002_username"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts start without a recovery code; they can create one while signed in.
    op.add_column("users", sa.Column("recovery_code_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_changed_at")
        batch.drop_column("recovery_code_hash")
