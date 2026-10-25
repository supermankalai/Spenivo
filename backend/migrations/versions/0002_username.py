"""sign in with a username instead of an email

Revision ID: 0002_username
Revises: 0001_initial
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_username"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    # Existing accounts keep their (lower-case) email as the username.
    with op.batch_alter_table("users") as batch:
        batch.alter_column("email", new_column_name="username", type_=sa.String(64), existing_nullable=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username", new_column_name="email", type_=sa.String(320), existing_nullable=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
