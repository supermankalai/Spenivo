"""Every user's data must be invisible and immutable to every other user."""

from conftest import make_tx


def test_users_cannot_see_or_change_each_others_transactions(client, alice, bob):
    a_tx = client.post("/api/v1/transactions", json=make_tx(merchant="Alice secret"), headers=alice).json()

    assert client.get("/api/v1/transactions", headers=bob).json()["total"] == 0
    assert (
        client.patch(f"/api/v1/transactions/{a_tx['id']}", json={"amount_minor_units": 1}, headers=bob).status_code
        == 404
    )
    assert client.delete(f"/api/v1/transactions/{a_tx['id']}", headers=bob).status_code == 404

    items = client.get("/api/v1/transactions", headers=alice).json()["items"]
    assert [(t["id"], t["amount_minor_units"]) for t in items] == [(a_tx["id"], 25000)]


def test_user_id_in_body_is_ignored(client, alice, bob):
    alice_id_guess = "alice"
    r = client.post("/api/v1/transactions", json={**make_tx(), "user_id": alice_id_guess}, headers=bob)
    assert r.status_code == 201
    assert client.get("/api/v1/transactions", headers=alice).json()["total"] == 0
    assert client.get("/api/v1/transactions", headers=bob).json()["total"] == 1


def test_same_client_id_is_separate_per_user(client, alice, bob):
    client.post("/api/v1/transactions", json=make_tx(id="shared-id", amount_minor_units=100), headers=alice)
    r = client.post("/api/v1/transactions", json=make_tx(id="shared-id", amount_minor_units=999), headers=bob)
    assert r.status_code == 201
    assert client.get("/api/v1/transactions", headers=alice).json()["items"][0]["amount_minor_units"] == 100


def test_sync_cannot_overwrite_or_read_other_users_rows(client, alice, bob):
    row = {**make_tx(id="tx-1", amount_minor_units=100), "created_at": 1, "updated_at": 1, "is_user_confirmed": True}
    client.post("/api/v1/sync", json={"cursor": None, "transactions": [row]}, headers=alice)
    attack = {**row, "amount_minor_units": 1, "updated_at": 999_999}
    resp = client.post("/api/v1/sync", json={"cursor": None, "transactions": [attack]}, headers=bob).json()
    assert [t["amount_minor_units"] for t in resp["transactions"]] == [1]  # Bob only sees his own copy

    alice_view = client.post("/api/v1/sync", json={"cursor": None}, headers=alice).json()
    assert [t["amount_minor_units"] for t in alice_view["transactions"]] == [100]


def test_insights_and_budgets_are_isolated(client, alice, bob):
    now = 1_741_766_400_000
    client.post("/api/v1/transactions", json=make_tx(transaction_datetime=now), headers=alice)
    client.put("/api/v1/budgets", json={"monthly_budget_minor": 5000}, headers=alice)
    summary = client.get(f"/api/v1/insights/summary?now={now}", headers=bob).json()
    assert summary["today"] == 0 and summary["budget"] is None
    assert client.get("/api/v1/budgets", headers=bob).json()["monthly_budget_minor"] is None
