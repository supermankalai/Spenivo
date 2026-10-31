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
    # Google account id ("sub" claim): the only login identifier. Null only for
    # accounts created before Google sign-in, which can no longer log in.
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
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
    # Monthly budget for this category (paise); null = none.
    budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
    # The usual daily budget; DayBudget rows override it for single days.
    daily_budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=0)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)


class DayBudget(Base):
    """A budget for one specific day (YYYY-MM-DD, IST). amount_minor null = override removed."""

    __tablename__ = "day_budgets"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day_key: Mapped[str] = mapped_column(String(10), primary_key=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (Index("ix_day_budgets_user_version", "user_id", "server_version"),)


class Reminder(Base):
    """An EMI or regular bill due on a fixed day each month."""

    __tablename__ = "reminders"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(60))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    due_day: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_month: Mapped[str] = mapped_column(String(7))
    total_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remind_days_before: Mapped[int] = mapped_column(Integer, default=1)
    # Reminders a day while unpaid (1-3), and what the notification's snooze button does.
    times_per_day: Mapped[int] = mapped_column(Integer, default=1)
    # The user's reminder times, minutes after midnight IST ("540,780,1080"); "" = defaults.
    remind_times: Mapped[str] = mapped_column(String(32), default="")
    snooze: Mapped[str] = mapped_column(String(8), default="1h")
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        CheckConstraint("kind IN ('emi', 'bill')", name="ck_reminders_kind"),
        Index("ix_reminders_user_version", "user_id", "server_version"),
    )


class Split(Base):
    """Part of an expense someone owes the user ("who owes you"); settled_at once repaid."""

    __tablename__ = "splits"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64))
    person: Mapped[str] = mapped_column(String(40))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    settled_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (Index("ix_splits_user_version", "user_id", "server_version"),)


class ReminderPayment(Base):
    """A month of an EMI/bill marked paid (deleted_at set when undone)."""

    __tablename__ = "reminder_payments"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    reminder_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_key: Mapped[str] = mapped_column(String(7), primary_key=True)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_expense: Mapped[bool] = mapped_column(Boolean, default=False)
    # Counted in the monthly budget (the user's answer when marking it paid).
    counted: Mapped[bool] = mapped_column(Boolean, default=True)
    paid_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    deleted_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (Index("ix_reminder_payments_user_version", "user_id", "server_version"),)


class BudgetOverrun(Base):
    """Why a day (YYYY-MM-DD) or month (YYYY-MM) went over budget, as the user told us."""

    __tablename__ = "budget_overruns"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(5), primary_key=True)
    period_key: Mapped[str] = mapped_column(String(10), primary_key=True)
    budget_minor: Mapped[int] = mapped_column(BigInteger)
    spent_minor: Mapped[int] = mapped_column(BigInteger)
    reason_code: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    server_version: Mapped[int] = mapped_column(BigInteger, default=0)

    __table_args__ = (
        CheckConstraint("scope IN ('day', 'month')", name="ck_budget_overruns_scope"),
        Index("ix_budget_overruns_user_version", "user_id", "server_version"),
    )
