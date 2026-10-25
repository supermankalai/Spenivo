from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token


def test_register_and_login(client):
    r = client.post("/api/v1/auth/register", json={"email": "  Asha@Example.com ", "password": "long-enough-pw"})
    assert r.status_code == 201
    assert r.json()["email"] == "asha@example.com"
    assert "password" not in r.text

    r = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "long-enough-pw"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_duplicate_email_rejected(client):
    body = {"email": "a@example.com", "password": "long-enough-pw"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    assert client.post("/api/v1/auth/register", json=body).status_code == 409


def test_weak_input_rejected(client):
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert (
        client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "long-enough-pw"}).status_code
        == 422
    )


def test_wrong_password_and_unknown_user_look_the_same(client):
    client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "long-enough-pw"})
    wrong = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "nope-nope-nope"})
    unknown = client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "nope-nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


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
