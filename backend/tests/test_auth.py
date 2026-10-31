from datetime import UTC, datetime, timedelta

from conftest import fake_google_token, make_tx

from app.core.security import create_access_token


def sign_in(client, token):
    return client.post("/api/v1/auth/google", json={"id_token": token})


def test_google_sign_in_creates_then_reuses_account(client):
    first = sign_in(client, fake_google_token("g-123", "asha@gmail.com", "Asha"))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["created"] is True
    assert body["user"]["email"] == "asha@gmail.com"
    assert body["user"]["name"] == "Asha"
    assert body["token_type"] == "bearer"

    again = sign_in(client, fake_google_token("g-123", "asha.new@gmail.com", "Asha"))
    assert again.json()["created"] is False
    assert again.json()["user"]["id"] == body["user"]["id"]

    headers = {"Authorization": f"Bearer {again.json()['access_token']}"}
    # Details follow the Google account.
    assert client.get("/api/v1/auth/me", headers=headers).json() == {
        "id": body["user"]["id"],
        "email": "asha.new@gmail.com",
        "name": "Asha",
    }


def test_identity_is_the_google_account_not_the_email(client):
    a = sign_in(client, fake_google_token("g-1", "a@gmail.com")).json()
    b = sign_in(client, fake_google_token("g-2", "a@gmail.com")).json()
    assert a["user"]["id"] != b["user"]["id"]


def test_invalid_google_token_rejected(client):
    r = sign_in(client, "not-a-real-google-token-at-all")
    assert r.status_code == 401
    assert r.json()["detail"] == "That Google sign-in didn’t work. Please try again."
    assert sign_in(client, "short").status_code == 422


def test_password_endpoints_are_gone(client):
    for path in ("/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/reset-password"):
        assert client.post(path, json={"mobile": "9876543210", "password": "long-enough"}).status_code == 404


def test_delete_account_removes_server_data(client, alice, bob):
    assert client.post("/api/v1/transactions", json=make_tx(), headers=alice).status_code == 201
    assert client.post("/api/v1/transactions", json=make_tx(), headers=bob).status_code == 201
    assert client.delete("/api/v1/auth/me", headers=alice).status_code == 204
    assert client.get("/api/v1/auth/me", headers=alice).status_code == 401
    assert client.get("/api/v1/transactions", headers=bob).json()["total"] == 1

    # Signing in again with the same Google account starts a new, empty account.
    fresh = sign_in(client, fake_google_token("google-alice-0001")).json()
    assert fresh["created"] is True
    headers = {"Authorization": f"Bearer {fresh['access_token']}"}
    assert client.get("/api/v1/transactions", headers=headers).json()["total"] == 0


def test_protected_routes_require_valid_token(client, alice):
    assert client.get("/api/v1/transactions").status_code == 401
    assert client.get("/api/v1/transactions", headers={"Authorization": "Bearer garbage"}).status_code == 401
    tampered = alice["Authorization"][:-2] + ("aa" if not alice["Authorization"].endswith("aa") else "bb")
    assert client.get("/api/v1/transactions", headers={"Authorization": tampered}).status_code == 401
    expired = create_access_token("someone", now=datetime.now(UTC) - timedelta(days=365))
    assert client.get("/api/v1/transactions", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    assert client.get("/api/v1/transactions", headers=alice).status_code == 200


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
