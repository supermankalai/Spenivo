"""sign in with a mobile number instead of a username

Revision ID: 0004_mobile_login
Revises: 0003_password_recovery
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_mobile_login"
down_revision = "0003_password_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    # Same width as before so no existing row can fail; new rows hold +91XXXXXXXXXX.
    # Accounts created with a username keep it here but cannot log in until re-created
    # with a mobile number (only test accounts existed when this changed).
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username", new_column_name="mobile", existing_type=sa.String(64), existing_nullable=False)
    op.create_index("ix_users_mobile", "users", ["mobile"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_mobile", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("mobile", new_column_name="username", existing_type=sa.String(64), existing_nullable=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
