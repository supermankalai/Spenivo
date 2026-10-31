from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db import get_db
from app.models import ProPayment, User
from app.services import pro


@pytest.fixture
def upi(monkeypatch):
    """Pro on sale: a UPI id is configured."""
    settings = get_settings()
    monkeypatch.setattr(settings, "pro_upi_id", "owner@okaxis")
    monkeypatch.setattr(settings, "pro_upi_name", "MyExpenses")
    return settings


def _db():
    return next(get_db())


def test_status_is_free_by_default(client, alice, upi):
    r = client.get("/api/v1/pro", headers=alice)
    assert r.status_code == 200
    body = r.json()
    assert body["is_pro"] is False and body["pro_until"] is None
    assert body["upi_id"] == "owner@okaxis"
    assert {p["plan"]: p["amount_minor"] for p in body["plans"]} == {"monthly": 4900, "yearly": 39900}
    assert body["open_payment"] is None


def test_requires_sign_in(client):
    assert client.get("/api/v1/pro").status_code == 401
    assert client.post("/api/v1/pro/payments", json={"plan": "monthly"}).status_code == 401


def test_cannot_buy_without_upi_id(client, alice):
    assert client.get("/api/v1/pro", headers=alice).json()["upi_id"] is None
    assert client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).status_code == 503


def test_pay_claim_approve_turns_pro_on(client, alice, upi):
    r = client.post("/api/v1/pro/payments", json={"plan": "yearly"}, headers=alice)
    assert r.status_code == 200
    payment = r.json()
    assert payment["code"].startswith("MX-") and payment["amount_minor"] == 39900 and payment["status"] == "pending"

    # Asking again for the same plan gives the same code.
    assert client.post("/api/v1/pro/payments", json={"plan": "yearly"}, headers=alice).json()["code"] == payment["code"]

    r = client.post(f"/api/v1/pro/payments/{payment['code']}/claim", json={"utr": "123456789012"}, headers=alice)
    assert r.status_code == 200 and r.json()["status"] == "claimed"
    assert client.get("/api/v1/pro", headers=alice).json()["open_payment"]["status"] == "claimed"

    db = _db()
    p = db.query(ProPayment).filter_by(code=payment["code"]).one()
    user = pro.approve(db, p)
    db.close()
    assert pro.aware(user.pro_until) > datetime.now(UTC) + timedelta(days=364)

    status = client.get("/api/v1/pro", headers=alice).json()
    assert status["is_pro"] is True
    assert status["open_payment"] is None
    assert status["last_payment"]["status"] == "approved"


def test_renewing_early_adds_to_remaining_time(client, alice, upi):
    db = _db()
    user = db.query(User).one()
    now = datetime.now(UTC)
    user.pro_until = now + timedelta(days=10)
    db.commit()
    code = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).json()["code"]
    user = pro.approve(db, db.query(ProPayment).filter_by(code=code).one(), now=now)
    assert pro.aware(user.pro_until) == now + timedelta(days=40)
    db.close()


def test_utr_must_be_12_digits_and_unused(client, alice, bob, upi):
    a = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).json()["code"]
    b = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=bob).json()["code"]
    assert (
        client.post(f"/api/v1/pro/payments/{a}/claim", json={"utr": "12345678901x"}, headers=alice).status_code == 400
    )
    assert (
        client.post(f"/api/v1/pro/payments/{a}/claim", json={"utr": "123456789012"}, headers=alice).status_code == 200
    )
    # The same UPI payment can't unlock two accounts.
    assert client.post(f"/api/v1/pro/payments/{b}/claim", json={"utr": "123456789012"}, headers=bob).status_code == 409


def test_cannot_claim_someone_elses_payment(client, alice, bob, upi):
    code = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).json()["code"]
    assert (
        client.post(f"/api/v1/pro/payments/{code}/claim", json={"utr": "123456789012"}, headers=bob).status_code == 404
    )


def test_rejected_payment_is_reported_and_stays_free(client, alice, upi):
    code = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).json()["code"]
    db = _db()
    pro.reject(db, db.query(ProPayment).filter_by(code=code).one())
    db.close()
    status = client.get("/api/v1/pro", headers=alice).json()
    assert status["is_pro"] is False
    assert status["last_payment"]["status"] == "rejected"
    assert (
        client.post(f"/api/v1/pro/payments/{code}/claim", json={"utr": "123456789012"}, headers=alice).status_code
        == 409
    )


def test_limits_open_payments(client, alice, upi):
    # Switching plans makes a new request each time; past the limit the server says wait.
    for plan in ("monthly", "yearly", "monthly"):
        assert client.post("/api/v1/pro/payments", json={"plan": plan}, headers=alice).status_code == 200
    assert client.post("/api/v1/pro/payments", json={"plan": "yearly"}, headers=alice).status_code == 429


def test_admin_grant_and_approve(client, alice, upi, capsys):
    from app import admin

    assert admin.main(["grant", "google-alice-0001@gmail.com", "30"]) == 0
    assert client.get("/api/v1/pro", headers=alice).json()["is_pro"] is True
    code = client.post("/api/v1/pro/payments", json={"plan": "monthly"}, headers=alice).json()["code"]
    assert admin.main(["pending"]) == 0
    assert code in capsys.readouterr().out
    assert admin.main(["approve", code.lower()]) == 0
    assert admin.main(["approve", code]) == 1  # already approved
