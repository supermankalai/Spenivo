"""
Pro paid by UPI, confirmed by hand.

1. The app asks for a payment: the server makes a short reference code ("MX-7K3P9").
2. The user pays the amount to the owner's UPI id with that code in the note, then
   reports the 12-digit UTR from their UPI app ("claimed").
3. The owner checks their bank/UPI app and approves (or rejects) with `python -m app.admin`.
   Approval extends `users.pro_until`; renewing early adds to the time already left.
"""

import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import ProPayment, User

PLAN_DAYS = {"monthly": 30, "yearly": 365}
# No 0/O, 1/I/L: the code is read off a phone screen and typed into a UPI note.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
UTR_PATTERN = re.compile(r"^\d{12}$")
# Open (unconfirmed) payments one account may have at once.
MAX_OPEN = 3


class ProError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; they were stored as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_pro(user: User, now: datetime | None = None) -> bool:
    until = aware(user.pro_until)
    return until is not None and until > (now or datetime.now(UTC))


def price_of(plan: str, settings: Settings) -> int:
    return settings.pro_price_yearly_minor if plan == "yearly" else settings.pro_price_monthly_minor


def _new_code(db: Session) -> str:
    while True:
        code = "MX-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))
        if db.execute(select(ProPayment.id).where(ProPayment.code == code)).first() is None:
            return code


def open_payment(db: Session, user: User) -> ProPayment | None:
    """The newest payment still waiting (to be paid, or to be confirmed)."""
    return db.execute(
        select(ProPayment)
        .where(ProPayment.user_id == user.id, ProPayment.status.in_(("pending", "claimed")))
        .order_by(ProPayment.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def start_payment(db: Session, user: User, plan: str, settings: Settings) -> ProPayment:
    if not settings.pro_upi_id:
        raise ProError("Pro can’t be bought right now.", 503)
    if plan not in PLAN_DAYS:
        raise ProError("Unknown plan.")
    # Reuse an unpaid request for the same plan, so tapping twice doesn't make two codes.
    current = open_payment(db, user)
    if current is not None and current.status == "pending" and current.plan == plan:
        return current
    open_count = db.execute(
        select(func.count())
        .select_from(ProPayment)
        .where(ProPayment.user_id == user.id, ProPayment.status.in_(("pending", "claimed")))
    ).scalar_one()
    if open_count >= MAX_OPEN:
        raise ProError("You have payments waiting to be confirmed. Please wait for those first.", 429)
    payment = ProPayment(user_id=user.id, code=_new_code(db), plan=plan, amount_minor=price_of(plan, settings))
    db.add(payment)
    db.commit()
    return payment


def claim_payment(db: Session, user: User, code: str, utr: str) -> ProPayment:
    utr = utr.strip()
    if not UTR_PATTERN.match(utr):
        raise ProError("The UPI reference (UTR) is the 12-digit number in your UPI app’s payment details.")
    payment = db.execute(
        select(ProPayment).where(ProPayment.code == code, ProPayment.user_id == user.id)
    ).scalar_one_or_none()
    if payment is None:
        raise ProError("Payment not found.", 404)
    if payment.status in ("approved", "rejected"):
        raise ProError("This payment has already been checked.", 409)
    used = db.execute(select(ProPayment.id).where(ProPayment.utr == utr, ProPayment.id != payment.id)).first()
    if used is not None:
        raise ProError("That UPI reference was already used for another payment.", 409)
    payment.utr = utr
    payment.status = "claimed"
    payment.claimed_at = datetime.now(UTC)
    db.commit()
    return payment


def approve(db: Session, payment: ProPayment, now: datetime | None = None) -> User:
    """Turn Pro on (or extend it) for the plan's length, counted from when the current Pro ends."""
    if payment.status not in ("pending", "claimed"):
        raise ProError(f"Payment {payment.code} is already {payment.status}.", 409)
    now = now or datetime.now(UTC)
    user = db.get(User, payment.user_id)
    assert user is not None
    start = max(now, aware(user.pro_until) or now)
    user.pro_until = start + timedelta(days=PLAN_DAYS[payment.plan])
    payment.status = "approved"
    payment.decided_at = now
    db.commit()
    return user


def reject(db: Session, payment: ProPayment) -> None:
    if payment.status not in ("pending", "claimed"):
        raise ProError(f"Payment {payment.code} is already {payment.status}.", 409)
    payment.status = "rejected"
    payment.decided_at = datetime.now(UTC)
    db.commit()
