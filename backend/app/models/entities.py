"""
Server-side copies of a user's data for optional sync.

Rows are keyed by (user_id, id): ids are generated on the phone, and the
composite key guarantees one user can never address another user's row even
if they guess or reuse an id. Timestamps are epoch milliseconds from the
client, used for last-writer-wins; `server_version` orders changes for pulls.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Login identifier: Indian mobile number in E.164 form (+91XXXXXXXXXX). Not yet OTP-verified.
    mobile: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Argon2 hash of the one-time recovery code (forgot password); null until one is issued.
    recovery_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Tokens issued before this moment are rejected (set on password change/reset).
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Monotonic per-user change counter; every accepted change gets the next value.
    sync_counter: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Category(Base):
    __tablename__ = "categories"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    icon: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16))
    counts_as_spending: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (Index("ix_categories_user_version", "user_id", "server_version"),)


class Transaction(Base):
    __tablename__ = "transactions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    amount_minor_units: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    transaction_type: Mapped[str] = mapped_column(String(16), default="expense")
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(16))
    transaction_datetime: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    source_package: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_user_confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        CheckConstraint("amount_minor_units > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("transaction_type IN ('expense', 'income')", name="ck_transactions_type"),
        CheckConstraint("status IN ('confirmed', 'pending_review', 'excluded')", name="ck_transactions_status"),
        Index("ix_transactions_user_datetime", "user_id", "transaction_datetime"),
        Index("ix_transactions_user_version", "user_id", "server_version"),
    )


class Budget(Base):
    __tablename__ = "budgets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    monthly_budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=0)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)
