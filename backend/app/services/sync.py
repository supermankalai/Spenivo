"""
Sync merge: last-writer-wins on the client's `updated_at` (ties keep the
server copy), deletions as tombstones, and a per-user monotonic counter as
the pull cursor.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, BudgetOverrun, Category, DayBudget, Reminder, ReminderPayment, Split, Transaction, User
from app.schemas import (
    SyncBudget,
    SyncCategory,
    SyncDayBudget,
    SyncOverrun,
    SyncReminder,
    SyncReminderPayment,
    SyncRequest,
    SyncResponse,
    SyncSplit,
    SyncTransaction,
)

_TX_FIELDS = [
    "amount_minor_units",
    "currency",
    "transaction_type",
    "category_id",
    "merchant",
    "description",
    "payment_method",
    "transaction_datetime",
    "source",
    "source_package",
    "external_reference",
    "status",
    "confidence",
    "is_user_confirmed",
    "created_at",
    "updated_at",
    "deleted_at",
]
_CAT_FIELDS = ["name", "icon", "color", "counts_as_spending", "is_archived", "sort_order", "budget_minor", "updated_at"]
_REMINDER_FIELDS = [
    "kind",
    "name",
    "amount_minor",
    "due_day",
    "category_id",
    "start_month",
    "total_months",
    "remind_days_before",
    "times_per_day",
    "remind_times",
    "snooze",
    "created_at",
    "updated_at",
    "deleted_at",
]
_PAYMENT_FIELDS = ["transaction_id", "created_expense", "counted", "paid_at", "updated_at", "deleted_at"]
_SPLIT_FIELDS = ["transaction_id", "person", "amount_minor", "settled_at", "created_at", "updated_at", "deleted_at"]
_OVERRUN_FIELDS = ["budget_minor", "spent_minor", "reason_code", "note", "created_at", "updated_at"]


def next_version(db: Session, user: User) -> int:
    user.sync_counter = (user.sync_counter or 0) + 1
    return user.sync_counter


def lock_user(db: Session, user_id: str) -> User:
    """Serialise concurrent syncs for one user (row lock on PostgreSQL)."""
    user = db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()
    return user


def apply_sync(db: Session, user_id: str, req: SyncRequest) -> SyncResponse:
    user = lock_user(db, user_id)
    since = req.cursor or 0

    for c in req.categories:
        existing = db.get(Category, (user.id, c.id))
        if existing is not None and existing.updated_at >= c.updated_at:
            continue
        if existing is None:
            existing = Category(user_id=user.id, id=c.id)
            db.add(existing)
        for f in _CAT_FIELDS:
            setattr(existing, f, getattr(c, f))
        existing.server_version = next_version(db, user)

    for t in req.transactions:
        existing_tx = db.get(Transaction, (user.id, t.id))
        if existing_tx is not None and existing_tx.updated_at >= t.updated_at:
            continue
        if existing_tx is None:
            existing_tx = Transaction(user_id=user.id, id=t.id)
            db.add(existing_tx)
        for f in _TX_FIELDS:
            setattr(existing_tx, f, getattr(t, f))
        existing_tx.server_version = next_version(db, user)

    if req.budget is not None:
        budget = db.get(Budget, user.id)
        if budget is None or budget.updated_at < req.budget.updated_at:
            if budget is None:
                budget = Budget(user_id=user.id)
                db.add(budget)
            budget.monthly_budget_minor = req.budget.monthly_budget_minor
            budget.daily_budget_minor = req.budget.daily_budget_minor
            budget.updated_at = req.budget.updated_at
            budget.server_version = next_version(db, user)

    for d in req.day_budgets:
        day = db.get(DayBudget, (user.id, d.day_key))
        if day is not None and day.updated_at >= d.updated_at:
            continue
        if day is None:
            day = DayBudget(user_id=user.id, day_key=d.day_key)
            db.add(day)
        day.amount_minor = d.amount_minor
        day.updated_at = d.updated_at
        day.server_version = next_version(db, user)

    for o in req.overruns:
        overrun = db.get(BudgetOverrun, (user.id, o.scope, o.period_key))
        if overrun is not None and overrun.updated_at >= o.updated_at:
            continue
        if overrun is None:
            overrun = BudgetOverrun(user_id=user.id, scope=o.scope, period_key=o.period_key)
            db.add(overrun)
        for f in _OVERRUN_FIELDS:
            setattr(overrun, f, getattr(o, f))
        overrun.server_version = next_version(db, user)

    for rm in req.reminders:
        reminder = db.get(Reminder, (user.id, rm.id))
        if reminder is not None and reminder.updated_at >= rm.updated_at:
            continue
        if reminder is None:
            reminder = Reminder(user_id=user.id, id=rm.id)
            db.add(reminder)
        for f in _REMINDER_FIELDS:
            setattr(reminder, f, getattr(rm, f))
        reminder.server_version = next_version(db, user)

    for pm in req.reminder_payments:
        payment = db.get(ReminderPayment, (user.id, pm.reminder_id, pm.period_key))
        if payment is not None and payment.updated_at >= pm.updated_at:
            continue
        if payment is None:
            payment = ReminderPayment(user_id=user.id, reminder_id=pm.reminder_id, period_key=pm.period_key)
            db.add(payment)
        for f in _PAYMENT_FIELDS:
            setattr(payment, f, getattr(pm, f))
        payment.server_version = next_version(db, user)

    for sp in req.splits:
        split = db.get(Split, (user.id, sp.id))
        if split is not None and split.updated_at >= sp.updated_at:
            continue
        if split is None:
            split = Split(user_id=user.id, id=sp.id)
            db.add(split)
        for f in _SPLIT_FIELDS:
            setattr(split, f, getattr(sp, f))
        split.server_version = next_version(db, user)

    db.flush()

    txs = db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id, Transaction.server_version > since)
        .order_by(Transaction.server_version)
    ).scalars()
    cats = db.execute(
        select(Category)
        .where(Category.user_id == user.id, Category.server_version > since)
        .order_by(Category.server_version)
    ).scalars()
    days = db.execute(
        select(DayBudget)
        .where(DayBudget.user_id == user.id, DayBudget.server_version > since)
        .order_by(DayBudget.server_version)
    ).scalars()
    overruns = db.execute(
        select(BudgetOverrun)
        .where(BudgetOverrun.user_id == user.id, BudgetOverrun.server_version > since)
        .order_by(BudgetOverrun.server_version)
    ).scalars()
    reminders = db.execute(
        select(Reminder)
        .where(Reminder.user_id == user.id, Reminder.server_version > since)
        .order_by(Reminder.server_version)
    ).scalars()
    payments = db.execute(
        select(ReminderPayment)
        .where(ReminderPayment.user_id == user.id, ReminderPayment.server_version > since)
        .order_by(ReminderPayment.server_version)
    ).scalars()
    splits = db.execute(
        select(Split).where(Split.user_id == user.id, Split.server_version > since).order_by(Split.server_version)
    ).scalars()
    budget = db.get(Budget, user.id)
    response = SyncResponse(
        cursor=user.sync_counter,
        transactions=[
            SyncTransaction.model_validate({"id": t.id, **{f: getattr(t, f) for f in _TX_FIELDS}}) for t in txs
        ],
        categories=[SyncCategory.model_validate({"id": c.id, **{f: getattr(c, f) for f in _CAT_FIELDS}}) for c in cats],
        budget=SyncBudget(
            monthly_budget_minor=budget.monthly_budget_minor,
            daily_budget_minor=budget.daily_budget_minor,
            updated_at=budget.updated_at,
        )
        if budget is not None and budget.server_version > since
        else None,
        day_budgets=[
            SyncDayBudget(day_key=d.day_key, amount_minor=d.amount_minor, updated_at=d.updated_at) for d in days
        ],
        overruns=[
            SyncOverrun.model_validate(
                {"scope": o.scope, "period_key": o.period_key, **{f: getattr(o, f) for f in _OVERRUN_FIELDS}}
            )
            for o in overruns
        ],
        reminders=[
            SyncReminder.model_validate({"id": r.id, **{f: getattr(r, f) for f in _REMINDER_FIELDS}}) for r in reminders
        ],
        reminder_payments=[
            SyncReminderPayment.model_validate(
                {
                    "reminder_id": p.reminder_id,
                    "period_key": p.period_key,
                    **{f: getattr(p, f) for f in _PAYMENT_FIELDS},
                }
            )
            for p in payments
        ],
        splits=[SyncSplit.model_validate({"id": s.id, **{f: getattr(s, f) for f in _SPLIT_FIELDS}}) for s in splits],
    )
    db.commit()
    return response
