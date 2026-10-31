"""
Owner commands for Pro payments. Run on the server:

    sudo -u myexpenses .venv/bin/python -m app.admin pending
    sudo -u myexpenses .venv/bin/python -m app.admin approve MX-7K3P9
    sudo -u myexpenses .venv/bin/python -m app.admin reject MX-7K3P9
    sudo -u myexpenses .venv/bin/python -m app.admin grant someone@gmail.com 30
    sudo -u myexpenses .venv/bin/python -m app.admin users

Before approving, find the payment in your bank/UPI app: same amount, and the UTR
(UPI reference) the user entered. The code is in the payment note when their UPI app kept it.
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db import get_db
from app.models import ProPayment, User
from app.services import pro


def _rupees(minor: int) -> str:
    return f"₹{minor / 100:,.0f}" if minor % 100 == 0 else f"₹{minor / 100:,.2f}"


def _when(dt: datetime | None) -> str:
    dt = pro.aware(dt)
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if dt else "-"


def cmd_pending(db) -> int:  # noqa: ANN001
    rows = db.execute(
        select(ProPayment, User)
        .join(User, User.id == ProPayment.user_id)
        .where(ProPayment.status.in_(("pending", "claimed")))
        .order_by(ProPayment.created_at)
    ).all()
    if not rows:
        print("No payments waiting.")
        return 0
    print(f"{'CODE':<10} {'STATUS':<8} {'PLAN':<8} {'AMOUNT':>7}  {'UTR':<13} {'USER':<32} CREATED")
    for p, u in rows:
        amount = _rupees(p.amount_minor)
        who = u.email or u.id
        print(f"{p.code:<10} {p.status:<8} {p.plan:<8} {amount:>7}  {p.utr or '-':<13} {who:<32} {_when(p.created_at)}")
    print("\n'claimed' = the user says they paid and gave a UTR. 'pending' = no UTR yet (maybe not paid).")
    return 0


def _find(db, code: str) -> ProPayment:  # noqa: ANN001
    payment = db.execute(select(ProPayment).where(ProPayment.code == code.strip().upper())).scalar_one_or_none()
    if payment is None:
        sys.exit(f"No payment with code {code}.")
    return payment


def cmd_approve(db, code: str) -> int:  # noqa: ANN001
    user = pro.approve(db, _find(db, code))
    print(f"Approved. {user.email or user.id} has Pro until {_when(user.pro_until)}.")
    return 0


def cmd_reject(db, code: str) -> int:  # noqa: ANN001
    pro.reject(db, _find(db, code))
    print("Rejected. The app will tell the user the payment couldn't be verified.")
    return 0


def cmd_grant(db, email: str, days: int) -> int:  # noqa: ANN001
    """Free Pro (a gift, a refund fix, a tester). Adds to any Pro time left."""
    user = db.execute(select(User).where(func.lower(User.email) == email.strip().lower())).scalar_one_or_none()
    if user is None:
        sys.exit(f"No account with email {email} (they must sign in to the app once).")
    now = datetime.now(UTC)
    user.pro_until = max(now, pro.aware(user.pro_until) or now) + timedelta(days=days)
    db.commit()
    print(f"{user.email} has Pro until {_when(user.pro_until)}.")
    return 0


def cmd_users(db) -> int:  # noqa: ANN001
    now = datetime.now(UTC)
    users = db.execute(select(User).where(User.pro_until.is_not(None)).order_by(User.pro_until.desc())).scalars().all()
    if not users:
        print("Nobody has had Pro yet.")
    for u in users:
        state = "Pro " if pro.is_pro(u, now) else "ended"
        print(f"{state}  until {_when(u.pro_until)}  {u.email or u.id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin", description="Confirm Pro payments made by UPI.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pending", help="payments waiting for you to check")
    sub.add_parser("approve", help="turn Pro on for a payment").add_argument("code")
    sub.add_parser("reject", help="the payment wasn't received").add_argument("code")
    g = sub.add_parser("grant", help="give Pro without a payment")
    g.add_argument("email")
    g.add_argument("days", type=int)
    sub.add_parser("users", help="everyone with Pro (now or before)")
    args = parser.parse_args(argv)

    db = next(get_db())
    try:
        if args.command == "pending":
            return cmd_pending(db)
        if args.command == "approve":
            return cmd_approve(db, args.code)
        if args.command == "reject":
            return cmd_reject(db, args.code)
        if args.command == "grant":
            return cmd_grant(db, args.email, args.days)
        return cmd_users(db)
    except pro.ProError as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
