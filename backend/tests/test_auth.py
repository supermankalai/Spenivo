from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token


def test_register_and_login(client):
    r = client.post("/api/v1/auth/register", json={"mobile": "98765 43210", "password": "long-enough"})
    assert r.status_code == 201
    assert r.json()["mobile"] == "+919876543210"
    assert "password" not in r.text

    # Any common format of the same number logs in.
    for variant in ("9876543210", "+91 98765-43210", "09876543210", "919876543210"):
        r = client.post("/api/v1/auth/login", json={"mobile": variant, "password": "long-enough"})
        assert r.status_code == 200, variant
    assert r.json()["token_type"] == "bearer"


def test_duplicate_mobile_rejected(client):
    assert (
        client.post("/api/v1/auth/register", json={"mobile": "9876543210", "password": "long-enough-pw"}).status_code
        == 201
    )
    r = client.post("/api/v1/auth/register", json={"mobile": "+91 98765 43210", "password": "other-password"})
    assert r.status_code == 409
    assert r.json()["detail"] == "An account with this mobile number already exists. Log in instead."


def test_invalid_input_rejected(client):
    assert client.post("/api/v1/auth/register", json={"mobile": "9876543210", "password": "short"}).status_code == 422
    # Too short/long, starts with 0-5, letters, foreign country code.
    for bad in ("98765", "98765432101", "5876543210", "98765abcde", "+44 7911 123456", "1234567890"):
        r = client.post("/api/v1/auth/register", json={"mobile": bad, "password": "long-enough-pw"})
        assert r.status_code == 422, bad


def test_wrong_password_and_unknown_user_look_the_same(client):
    client.post("/api/v1/auth/register", json={"mobile": "9876543210", "password": "long-enough-pw"})
    wrong = client.post("/api/v1/auth/login", json={"mobile": "9876543210", "password": "nope-nope-nope"})
    unknown = client.post("/api/v1/auth/login", json={"mobile": "9123456789", "password": "nope-nope-nope"})
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
