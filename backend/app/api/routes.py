import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_recovery_code,
    hash_password,
    hash_recovery_code,
    verify_password,
    verify_recovery_code,
)
from app.models import Budget, Category, Transaction, User
from app.schemas import (
    BudgetIn,
    BudgetOut,
    CategoryTotalOut,
    ChangePasswordIn,
    ConfirmPasswordIn,
    Credentials,
    LoginRequest,
    RecoveryCodeOut,
    RegisterOut,
    ResetPasswordIn,
    ResetPasswordOut,
    SummaryOut,
    SyncRequest,
    SyncResponse,
    TokenOut,
    TransactionCreate,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services import insights
from app.services.sync import apply_sync, lock_user, next_version

router = APIRouter(prefix="/api/v1")

# Precomputed so failed logins for unknown numbers take as long as wrong passwords.
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def _now_ms() -> int:
    return int(time.time() * 1000)


# --- auth -----------------------------------------------------------------


@router.post("/auth/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(body: Credentials, db: DbSession) -> RegisterOut:
    code = generate_recovery_code()
    user = User(
        mobile=body.mobile, password_hash=hash_password(body.password), recovery_code_hash=hash_recovery_code(code)
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this mobile number already exists. Log in instead."
        ) from None
    return RegisterOut(id=user.id, mobile=user.mobile, recovery_code=code)


def _set_password(user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    # Tokens issued before now stop working: other devices are signed out.
    user.password_changed_at = datetime.now(UTC).replace(microsecond=0)


@router.post("/auth/reset-password", response_model=ResetPasswordOut, tags=["auth"])
def reset_password(body: ResetPasswordIn, db: DbSession) -> ResetPasswordOut:
    """Forgot password: mobile number + recovery code → new password. The code is single-use."""
    user = db.execute(select(User).where(User.mobile == body.mobile)).scalar_one_or_none()
    code_hash = user.recovery_code_hash if user is not None and user.recovery_code_hash else _DUMMY_HASH
    valid = verify_recovery_code(body.recovery_code, code_hash)
    if user is None or user.recovery_code_hash is None or not valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That mobile number and recovery code don’t match.")
    _set_password(user, body.new_password)
    new_code = generate_recovery_code()
    user.recovery_code_hash = hash_recovery_code(new_code)
    db.commit()
    return ResetPasswordOut(access_token=create_access_token(user.id), recovery_code=new_code)


@router.post("/auth/change-password", response_model=TokenOut, tags=["auth"])
def change_password(body: ChangePasswordIn, user: CurrentUser, db: DbSession) -> TokenOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not right.")
    _set_password(user, body.new_password)
    db.commit()
    # This device stays signed in with a fresh token.
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/auth/recovery-code", response_model=RecoveryCodeOut, tags=["auth"])
def new_recovery_code(body: ConfirmPasswordIn, user: CurrentUser, db: DbSession) -> RecoveryCodeOut:
    """Issue a new recovery code (the old one stops working). Needs the password, not just a token."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is not right.")
    code = generate_recovery_code()
    user.recovery_code_hash = hash_recovery_code(code)
    db.commit()
    return RecoveryCodeOut(recovery_code=code)


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(body: LoginRequest, db: DbSession) -> TokenOut:
    user = db.execute(select(User).where(User.mobile == body.mobile)).scalar_one_or_none()
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect mobile number or password.")
    return TokenOut(access_token=create_access_token(user.id))


# --- transactions ---------------------------------------------------------


def _get_owned(db: DbSession, user: User, transaction_id: str) -> Transaction:
    tx = db.get(Transaction, (user.id, transaction_id))
    if tx is None or tx.deleted_at is not None:
        # 404 (not 403) so ids of other users' rows are not confirmed to exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found.")
    return tx


@router.get("/transactions", response_model=TransactionPage, tags=["transactions"])
def list_transactions(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    start: Annotated[int | None, Query(ge=0, description="Inclusive epoch ms")] = None,
    end: Annotated[int | None, Query(ge=0, description="Exclusive epoch ms")] = None,
    tx_status: Annotated[str | None, Query(alias="status", pattern="^(confirmed|pending_review|excluded)$")] = None,
) -> TransactionPage:
    conditions = [Transaction.user_id == user.id, Transaction.deleted_at.is_(None)]
    if start is not None:
        conditions.append(Transaction.transaction_datetime >= start)
    if end is not None:
        conditions.append(Transaction.transaction_datetime < end)
    if tx_status is not None:
        conditions.append(Transaction.status == tx_status)
    total = db.execute(select(func.count()).select_from(Transaction).where(*conditions)).scalar_one()
    rows = db.execute(
        select(Transaction)
        .where(*conditions)
        .order_by(Transaction.transaction_datetime.desc(), Transaction.id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return TransactionPage(
        items=[TransactionOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/transactions", response_model=TransactionOut, status_code=status.HTTP_201_CREATED, tags=["transactions"])
def create_transaction(body: TransactionCreate, user: CurrentUser, db: DbSession) -> TransactionOut:
    locked = lock_user(db, user.id)
    tx_id = body.id or str(uuid.uuid4())
    if db.get(Transaction, (user.id, tx_id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A transaction with this id already exists.")
    now = _now_ms()
    tx = Transaction(
        user_id=user.id,
        id=tx_id,
        **body.model_dump(exclude={"id"}),
        created_at=now,
        updated_at=now,
        server_version=next_version(db, locked),
    )
    db.add(tx)
    db.commit()
    return TransactionOut.model_validate(tx)


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut, tags=["transactions"])
def update_transaction(
    transaction_id: str, body: TransactionUpdate, user: CurrentUser, db: DbSession
) -> TransactionOut:
    locked = lock_user(db, user.id)
    tx = _get_owned(db, user, transaction_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field not in {"category_id", "merchant", "description"}:
            raise HTTPException(422, f"{field} cannot be null.")
        setattr(tx, field, value)
    tx.updated_at = max(_now_ms(), tx.updated_at + 1)
    tx.server_version = next_version(db, locked)
    db.commit()
    return TransactionOut.model_validate(tx)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["transactions"])
def delete_transaction(transaction_id: str, user: CurrentUser, db: DbSession) -> Response:
    locked = lock_user(db, user.id)
    tx = _get_owned(db, user, transaction_id)
    now = max(_now_ms(), tx.updated_at + 1)
    tx.deleted_at = now
    tx.updated_at = now
    tx.server_version = next_version(db, locked)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- insights -------------------------------------------------------------


def _load_for_insights(
    db: DbSession, user: User, start: int, end: int
) -> tuple[list[insights.Tx], set[str], dict[str, str]]:
    rows = db.execute(
        select(Transaction).where(
            Transaction.user_id == user.id,
            Transaction.deleted_at.is_(None),
            Transaction.transaction_datetime >= start,
            Transaction.transaction_datetime < end,
        )
    ).scalars()
    txs = [
        insights.Tx(
            r.amount_minor_units, r.transaction_datetime, r.status, r.transaction_type, r.category_id, r.deleted_at
        )
        for r in rows
    ]
    cats = db.execute(select(Category).where(Category.user_id == user.id)).scalars().all()
    # Without synced categories, fall back to the app default: Transfers is not spending.
    excluded = {c.id for c in cats if not c.counts_as_spending} if cats else {"transfers"}
    names = {c.id: c.name for c in cats}
    return txs, excluded, names


@router.get("/insights/summary", response_model=SummaryOut, tags=["insights"])
def insights_summary(
    user: CurrentUser,
    db: DbSession,
    now: Annotated[int | None, Query(ge=0, description="Override 'now' (epoch ms) for testing")] = None,
) -> SummaryOut:
    now_ms = now if now is not None else _now_ms()
    txs, excluded, _ = _load_for_insights(
        db, user, insights.start_of_previous_month(now_ms), insights.start_of_next_month(now_ms)
    )
    s = insights.build_summary(txs, excluded, now_ms)
    budget = db.get(Budget, user.id)
    limit = budget.monthly_budget_minor if budget else None
    return SummaryOut(
        today=s.today,
        week=s.week,
        month=s.month,
        daily_average=s.daily_average,
        days_elapsed=s.days_elapsed,
        budget=limit,
        budget_remaining=(limit - s.month) if limit else None,
        previous_month_same_period=s.previous_month_same_period,
        change_percent=s.change_percent,
        period_label=s.period_label,
    )


@router.get("/insights/categories", response_model=list[CategoryTotalOut], tags=["insights"])
def insights_categories(
    user: CurrentUser,
    db: DbSession,
    now: Annotated[int | None, Query(ge=0, description="Any instant inside the month (epoch ms)")] = None,
) -> list[CategoryTotalOut]:
    now_ms = now if now is not None else _now_ms()
    start, end = insights.start_of_month(now_ms), insights.start_of_next_month(now_ms)
    txs, excluded, names = _load_for_insights(db, user, start, end)
    return [
        CategoryTotalOut(
            category_id=cid, name=names.get(cid or "", cid or "Uncategorised"), total=t, count=n, percent=p
        )
        for cid, t, n, p in insights.category_breakdown(txs, excluded, start, end)
    ]


# --- budgets --------------------------------------------------------------


@router.get("/budgets", response_model=BudgetOut, tags=["budgets"])
def get_budget(user: CurrentUser, db: DbSession) -> BudgetOut:
    budget = db.get(Budget, user.id)
    return BudgetOut(
        monthly_budget_minor=budget.monthly_budget_minor if budget else None,
        updated_at=budget.updated_at if budget else 0,
    )


@router.put("/budgets", response_model=BudgetOut, tags=["budgets"])
def put_budget(body: BudgetIn, user: CurrentUser, db: DbSession) -> BudgetOut:
    locked = lock_user(db, user.id)
    budget = db.get(Budget, user.id)
    if budget is None:
        budget = Budget(user_id=user.id, updated_at=0)
        db.add(budget)
    budget.monthly_budget_minor = body.monthly_budget_minor
    budget.updated_at = max(_now_ms(), budget.updated_at + 1)
    budget.server_version = next_version(db, locked)
    db.commit()
    return BudgetOut(monthly_budget_minor=budget.monthly_budget_minor, updated_at=budget.updated_at)


# --- sync -----------------------------------------------------------------


@router.post("/sync", response_model=SyncResponse, tags=["sync"])
def sync(body: SyncRequest, user: CurrentUser, db: DbSession) -> SyncResponse:
    limit = get_settings().sync_max_batch
    if len(body.transactions) > limit or len(body.categories) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Send at most {limit} rows per sync.")
    return apply_sync(db, user.id, body)
