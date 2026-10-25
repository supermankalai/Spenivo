"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-25
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("sync_counter", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "categories",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("icon", sa.String(64), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("counts_as_spending", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_categories_user_version", "categories", ["user_id", "server_version"])

    op.create_table(
        "transactions",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("amount_minor_units", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("transaction_type", sa.String(16), nullable=False),
        sa.Column("category_id", sa.String(64), nullable=True),
        sa.Column("merchant", sa.String(120), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("payment_method", sa.String(16), nullable=False),
        sa.Column("transaction_datetime", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_package", sa.String(255), nullable=True),
        sa.Column("external_reference", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_user_confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("amount_minor_units > 0", name="ck_transactions_amount_positive"),
        sa.CheckConstraint("transaction_type IN ('expense', 'income')", name="ck_transactions_type"),
        sa.CheckConstraint("status IN ('confirmed', 'pending_review', 'excluded')", name="ck_transactions_status"),
    )
    op.create_index("ix_transactions_user_datetime", "transactions", ["user_id", "transaction_datetime"])
    op.create_index("ix_transactions_user_version", "transactions", ["user_id", "server_version"])

    op.create_table(
        "budgets",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("monthly_budget_minor", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("server_version", sa.BigInteger(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("budgets")
    op.drop_index("ix_transactions_user_version", table_name="transactions")
    op.drop_index("ix_transactions_user_datetime", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_categories_user_version", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
