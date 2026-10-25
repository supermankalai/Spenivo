"""
Sync merge: last-writer-wins on the client's `updated_at` (ties keep the
server copy), deletions as tombstones, and a per-user monotonic counter as
the pull cursor.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, Transaction, User
from app.schemas import SyncBudget, SyncCategory, SyncRequest, SyncResponse, SyncTransaction

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
_CAT_FIELDS = ["name", "icon", "color", "counts_as_spending", "is_archived", "sort_order", "updated_at"]


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
            budget.updated_at = req.budget.updated_at
            budget.server_version = next_version(db, user)

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
    budget = db.get(Budget, user.id)
    response = SyncResponse(
        cursor=user.sync_counter,
        transactions=[
            SyncTransaction.model_validate({"id": t.id, **{f: getattr(t, f) for f in _TX_FIELDS}}) for t in txs
        ],
        categories=[SyncCategory.model_validate({"id": c.id, **{f: getattr(c, f) for f in _CAT_FIELDS}}) for c in cats],
        budget=SyncBudget(monthly_budget_minor=budget.monthly_budget_minor, updated_at=budget.updated_at)
        if budget is not None and budget.server_version > since
        else None,
    )
    db.commit()
    return response
