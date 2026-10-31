from datetime import datetime

from conftest import make_tx

from app.services.insights import IST, start_of_day, start_of_week


def ist(y, m, d, h=12, mi=0) -> int:
    return int(datetime(y, m, d, h, mi, tzinfo=IST).timestamp() * 1000)


def row(id_, updated_at, **kw):
    return {
        **make_tx(id=id_, **kw),
        "created_at": 1,
        "updated_at": updated_at,
        "is_user_confirmed": True,
        "deleted_at": kw.get("deleted_at"),
    }


def test_two_devices_converge(client, alice):
    phone = client.post(
        "/api/v1/sync", json={"cursor": None, "transactions": [row("t1", 10), row("t2", 10)]}, headers=alice
    ).json()
    assert len(phone["transactions"]) == 2

    tablet = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert {t["id"] for t in tablet["transactions"]} == {"t1", "t2"}
    cursor = tablet["cursor"]

    # Tablet edits t1 later; phone deletes t2.
    client.post(
        "/api/v1/sync", json={"cursor": cursor, "transactions": [row("t1", 20, amount_minor_units=500)]}, headers=alice
    )
    client.post(
        "/api/v1/sync", json={"cursor": phone["cursor"], "transactions": [row("t2", 30, deleted_at=30)]}, headers=alice
    )

    later = client.post("/api/v1/sync", json={"cursor": cursor}, headers=alice).json()
    changed = {t["id"]: t for t in later["transactions"]}
    assert changed["t1"]["amount_minor_units"] == 500
    assert changed["t2"]["deleted_at"] == 30
    assert later["cursor"] > cursor

    # Nothing new since the latest cursor.
    assert client.post("/api/v1/sync", json={"cursor": later["cursor"]}, headers=alice).json()["transactions"] == []


def test_last_writer_wins_and_stale_writes_are_ignored(client, alice):
    client.post("/api/v1/sync", json={"transactions": [row("t1", 100, amount_minor_units=100)]}, headers=alice)
    client.post("/api/v1/sync", json={"transactions": [row("t1", 50, amount_minor_units=999)]}, headers=alice)  # stale
    client.post(
        "/api/v1/sync", json={"transactions": [row("t1", 100, amount_minor_units=777)]}, headers=alice
    )  # tie: server keeps
    state = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert state["transactions"][0]["amount_minor_units"] == 100


def test_budget_and_categories_sync(client, alice):
    cat = {
        "id": "pets",
        "name": "Pets",
        "icon": "paw",
        "color": "#123456",
        "counts_as_spending": True,
        "is_archived": False,
        "sort_order": 12,
        "budget_minor": 600_000,
        "updated_at": 5,
    }
    r = client.post(
        "/api/v1/sync",
        json={"categories": [cat], "budget": {"monthly_budget_minor": 1_500_000, "updated_at": 5}},
        headers=alice,
    ).json()
    assert r["categories"][0]["name"] == "Pets"
    assert r["categories"][0]["budget_minor"] == 600_000
    assert r["budget"]["monthly_budget_minor"] == 1_500_000
    assert client.get("/api/v1/budgets", headers=alice).json()["monthly_budget_minor"] == 1_500_000


def test_sync_validates_rows(client, alice):
    bad = row("t1", 1, amount_minor_units=0)
    assert client.post("/api/v1/sync", json={"transactions": [bad]}, headers=alice).status_code == 422
    assert client.post("/api/v1/sync", json={"transactions": [row("../etc", 1)]}, headers=alice).status_code == 422


def test_ist_boundaries():
    # 00:15 IST on 5 Mar is still 4 Mar in UTC.
    assert start_of_day(ist(2025, 3, 5, 0, 15)) == ist(2025, 3, 5, 0)
    assert start_of_week(ist(2025, 3, 9, 22)) == ist(2025, 3, 3, 0)  # Sunday -> Monday


def test_summary_counts_only_confirmed_spending(client, alice):
    now = ist(2025, 3, 12, 18)
    for body in (
        make_tx(
            amount_minor_units=25000, transaction_datetime=ist(2025, 3, 12, 0, 5)
        ),  # today (just after IST midnight)
        make_tx(amount_minor_units=1000, transaction_datetime=ist(2025, 3, 11, 23, 50)),  # yesterday
        make_tx(amount_minor_units=70000, transaction_datetime=ist(2025, 3, 3)),  # this month
        make_tx(amount_minor_units=99999, transaction_datetime=now, status="pending_review"),
        make_tx(amount_minor_units=88888, transaction_datetime=now, status="excluded"),
        make_tx(amount_minor_units=55555, transaction_datetime=now, category_id="transfers"),
        make_tx(amount_minor_units=44444, transaction_datetime=now, transaction_type="income"),
        make_tx(amount_minor_units=48000, transaction_datetime=ist(2025, 2, 5)),  # last month, comparable window
        make_tx(amount_minor_units=10000, transaction_datetime=ist(2025, 2, 20)),  # last month, outside window
    ):
        assert client.post("/api/v1/transactions", json=body, headers=alice).status_code == 201
    client.put("/api/v1/budgets", json={"monthly_budget_minor": 100000}, headers=alice)

    s = client.get(f"/api/v1/insights/summary?now={now}", headers=alice).json()
    assert s["today"] == 25000
    assert s["week"] == 26000  # week began Monday 10 Mar
    assert s["month"] == 96000
    assert s["daily_average"] == 8000
    assert s["budget_remaining"] == 4000
    assert s["previous_month_same_period"] == 48000
    assert s["change_percent"] == 100
    assert s["period_label"] == "Day 1–12 of this month vs day 1–12 of last month"

    cats = client.get(f"/api/v1/insights/categories?now={now}", headers=alice).json()
    assert cats == [{"category_id": "food", "name": "food", "total": 96000, "count": 3, "percent": 100}]


def test_rounding_matches_javascript_math_round():
    from app.services.insights import round_half_up

    # JS: Math.round(2.5) === 3, Math.round(-2.5) === -2, Math.round(-2.6) === -3
    assert round_half_up(5, 2) == 3
    assert round_half_up(-5, 2) == -2
    assert round_half_up(-13, 5) == -3
    assert round_half_up(7, 3) == 2


def test_daily_budgets_and_overrun_reasons_sync(client, alice):
    client.post(
        "/api/v1/sync",
        json={
            "cursor": None,
            "budget": {"monthly_budget_minor": 3_000_000, "daily_budget_minor": 100_000, "updated_at": 5},
            "day_budgets": [{"day_key": "2026-10-26", "amount_minor": 50_000, "updated_at": 5}],
            "overruns": [
                {
                    "scope": "day",
                    "period_key": "2026-10-25",
                    "budget_minor": 100_000,
                    "spent_minor": 130_000,
                    "reason_code": "eating_out",
                    "note": "Birthday",
                    "created_at": 5,
                    "updated_at": 5,
                },
            ],
        },
        headers=alice,
    )

    other_phone = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert other_phone["budget"]["daily_budget_minor"] == 100_000
    assert other_phone["day_budgets"] == [{"day_key": "2026-10-26", "amount_minor": 50_000, "updated_at": 5}]
    assert other_phone["overruns"][0]["note"] == "Birthday"

    # Removing a day's budget travels as amount null; an older edit loses.
    client.post(
        "/api/v1/sync",
        json={
            "cursor": other_phone["cursor"],
            "day_budgets": [{"day_key": "2026-10-26", "amount_minor": None, "updated_at": 9}],
        },
        headers=alice,
    )
    client.post(
        "/api/v1/sync",
        json={"day_budgets": [{"day_key": "2026-10-26", "amount_minor": 70_000, "updated_at": 7}]},
        headers=alice,
    )
    latest = client.post("/api/v1/sync", json={"cursor": other_phone["cursor"]}, headers=alice).json()
    assert latest["day_budgets"] == [{"day_key": "2026-10-26", "amount_minor": None, "updated_at": 9}]


def test_overrun_period_key_must_match_scope(client, alice):
    bad = {
        "scope": "month",
        "period_key": "2026-10-25",
        "budget_minor": 1,
        "spent_minor": 2,
        "reason_code": "other",
        "created_at": 1,
        "updated_at": 1,
    }
    assert client.post("/api/v1/sync", json={"overruns": [bad]}, headers=alice).status_code == 422


def test_emi_reminders_and_paid_months_sync(client, alice, bob):
    loan = {
        "id": "rem-1",
        "kind": "emi",
        "name": "Car loan",
        "amount_minor": 1_250_000,
        "due_day": 5,
        "category_id": "loans",
        "start_month": "2026-10",
        "total_months": 36,
        "remind_days_before": 1,
        "times_per_day": 3,
        "remind_times": "480,840,1290",
        "snooze": "15m",
        "created_at": 1,
        "updated_at": 1,
    }
    paid = {
        "reminder_id": "rem-1",
        "period_key": "2026-10",
        "transaction_id": "tx-9",
        "created_expense": True,
        "counted": False,
        "paid_at": 2,
        "updated_at": 2,
    }
    client.post("/api/v1/sync", json={"reminders": [loan], "reminder_payments": [paid]}, headers=alice)

    other_phone = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert other_phone["reminders"][0]["name"] == "Car loan"
    assert other_phone["reminders"][0]["times_per_day"] == 3
    assert other_phone["reminders"][0]["snooze"] == "15m"
    assert other_phone["reminders"][0]["remind_times"] == "480,840,1290"
    assert other_phone["reminder_payments"][0]["period_key"] == "2026-10"
    assert other_phone["reminder_payments"][0]["counted"] is False

    # Undo travels as a tombstone; another user sees nothing.
    client.post("/api/v1/sync", json={"reminder_payments": [{**paid, "updated_at": 3, "deleted_at": 3}]}, headers=alice)
    latest = client.post("/api/v1/sync", json={"cursor": other_phone["cursor"]}, headers=alice).json()
    assert latest["reminder_payments"][0]["deleted_at"] == 3
    theirs = client.post("/api/v1/sync", json={"cursor": None}, headers=bob).json()
    assert theirs["reminders"] == [] and theirs["reminder_payments"] == []


def test_splits_sync_per_user(client, alice, bob):
    split = {
        "id": "sp-1",
        "transaction_id": "tx-1",
        "person": "Rahul",
        "amount_minor": 40_000,
        "created_at": 1,
        "updated_at": 1,
    }
    client.post("/api/v1/sync", json={"splits": [split]}, headers=alice)
    other_phone = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert other_phone["splits"][0]["person"] == "Rahul"
    assert other_phone["splits"][0]["settled_at"] is None

    # Settling travels as an update; another user sees nothing.
    client.post("/api/v1/sync", json={"splits": [{**split, "settled_at": 5, "updated_at": 5}]}, headers=alice)
    latest = client.post("/api/v1/sync", json={"cursor": other_phone["cursor"]}, headers=alice).json()
    assert latest["splits"][0]["settled_at"] == 5
    assert client.post("/api/v1/sync", json={"cursor": None}, headers=bob).json()["splits"] == []
