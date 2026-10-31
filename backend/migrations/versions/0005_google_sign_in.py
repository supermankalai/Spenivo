"""Google sign-in replaces mobile + password; daily budgets and over-budget reasons
are synced too

Revision ID: 0005_google_sign_in
Revises: 0004_mobile_login
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_google_sign_in"
down_revision = "0004_mobile_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_mobile", table_name="users")
    # Password accounts cannot sign in any more (no Google id). Their rows stay so
    # nothing is silently deleted; an operator can remove them.
    with op.batch_alter_table("users") as batch:
        batch.drop_column("mobile")
        batch.drop_column("password_hash")
        batch.drop_column("recovery_code_hash")
        batch.drop_column("password_changed_at")
        batch.add_column(sa.Column("google_sub", sa.String(255), nullable=True))
        batch.add_column(sa.Column("email", sa.String(320), nullable=True))
        batch.add_column(sa.Column("name", sa.String(120), nullable=True))
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    with op.batch_alter_table("budgets") as batch:
        batch.add_column(sa.Column("daily_budget_minor", sa.BigInteger(), nullable=True))

    op.create_table(
        "day_budgets",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day_key", sa.String(10), primary_key=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_day_budgets_user_version", "day_budgets", ["user_id", "server_version"])

    op.create_table(
        "budget_overruns",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("scope", sa.String(5), primary_key=True),
        sa.Column("period_key", sa.String(10), primary_key=True),
        sa.Column("budget_minor", sa.BigInteger(), nullable=False),
        sa.Column("spent_minor", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("scope IN ('day', 'month')", name="ck_budget_overruns_scope"),
    )
    op.create_index("ix_budget_overruns_user_version", "budget_overruns", ["user_id", "server_version"])


def downgrade() -> None:
    op.drop_index("ix_budget_overruns_user_version", table_name="budget_overruns")
    op.drop_table("budget_overruns")
    op.drop_index("ix_day_budgets_user_version", table_name="day_budgets")
    op.drop_table("day_budgets")
    with op.batch_alter_table("budgets") as batch:
        batch.drop_column("daily_budget_minor")
    # Google accounts have no mobile number or password to go back to.
    op.execute("DELETE FROM users")
    op.drop_index("ix_users_google_sub", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("name")
        batch.drop_column("email")
        batch.drop_column("google_sub")
        batch.add_column(sa.Column("mobile", sa.String(64), nullable=False))
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=False))
        batch.add_column(sa.Column("recovery_code_hash", sa.String(255), nullable=True))
        batch.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_mobile", "users", ["mobile"], unique=True)
