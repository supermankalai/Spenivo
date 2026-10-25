from conftest import make_tx


def test_crud_flow(client, alice):
    r = client.post("/api/v1/transactions", json=make_tx(), headers=alice)
    assert r.status_code == 201, r.text
    tx = r.json()
    assert tx["amount_minor_units"] == 25000
    assert tx["currency"] == "INR"

    r = client.patch(
        f"/api/v1/transactions/{tx['id']}",
        json={"amount_minor_units": 30050, "category_id": "groceries"},
        headers=alice,
    )
    assert r.status_code == 200
    assert r.json()["amount_minor_units"] == 30050
    assert r.json()["updated_at"] > tx["updated_at"] - 1

    assert client.delete(f"/api/v1/transactions/{tx['id']}", headers=alice).status_code == 204
    assert (
        client.patch(f"/api/v1/transactions/{tx['id']}", json={"amount_minor_units": 1}, headers=alice).status_code
        == 404
    )
    assert client.get("/api/v1/transactions", headers=alice).json()["total"] == 0


def test_client_supplied_id(client, alice):
    r = client.post("/api/v1/transactions", json=make_tx(id="phone-uuid-1"), headers=alice)
    assert r.json()["id"] == "phone-uuid-1"
    assert client.post("/api/v1/transactions", json=make_tx(id="phone-uuid-1"), headers=alice).status_code == 409


def test_validation(client, alice):
    for bad in (
        make_tx(amount_minor_units=0),
        make_tx(amount_minor_units=-5),
        make_tx(amount_minor_units=12.5),
        make_tx(payment_method="bitcoin"),
        make_tx(currency="USD"),
        make_tx(status="failed"),
    ):
        assert client.post("/api/v1/transactions", json=bad, headers=alice).status_code == 422, bad
    created = client.post("/api/v1/transactions", json=make_tx(), headers=alice).json()
    assert (
        client.patch(
            f"/api/v1/transactions/{created['id']}", json={"amount_minor_units": None}, headers=alice
        ).status_code
        == 422
    )
    assert (
        client.patch(f"/api/v1/transactions/{created['id']}", json={"user_id": "x"}, headers=alice).status_code == 422
    )


def test_pagination_and_filters(client, alice):
    for i in range(5):
        client.post(
            "/api/v1/transactions",
            json=make_tx(transaction_datetime=1_000_000 + i, status="pending_review" if i == 4 else "confirmed"),
            headers=alice,
        )
    page = client.get("/api/v1/transactions?limit=2&offset=0", headers=alice).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    assert page["items"][0]["transaction_datetime"] == 1_000_004  # newest first
    page2 = client.get("/api/v1/transactions?limit=2&offset=4", headers=alice).json()
    assert len(page2["items"]) == 1
    assert client.get("/api/v1/transactions?status=pending_review", headers=alice).json()["total"] == 1
    assert client.get("/api/v1/transactions?start=1000001&end=1000003", headers=alice).json()["total"] == 2
    assert client.get("/api/v1/transactions?limit=1000", headers=alice).status_code == 422


def test_budget(client, alice):
    assert client.get("/api/v1/budgets", headers=alice).json() == {"monthly_budget_minor": None, "updated_at": 0}
    r = client.put("/api/v1/budgets", json={"monthly_budget_minor": 3_000_000}, headers=alice)
    assert r.json()["monthly_budget_minor"] == 3_000_000
    assert client.put("/api/v1/budgets", json={"monthly_budget_minor": 0}, headers=alice).status_code == 422
