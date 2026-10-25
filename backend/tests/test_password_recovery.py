import time


def register(client, mobile="9876543210", password="first-password"):
    r = client.post("/api/v1/auth/register", json={"mobile": mobile, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, mobile="9876543210", password="first-password"):
    return client.post("/api/v1/auth/login", json={"mobile": mobile, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_a_readable_recovery_code(client):
    code = register(client)["recovery_code"]
    parts = code.split("-")
    assert len(parts) == 4 and all(len(p) == 4 for p in parts)
    assert not set(code) & set("01ILO")  # no look-alike characters


def test_reset_password_with_recovery_code(client):
    code = register(client)["recovery_code"]
    old_token = login(client).json()["access_token"]
    time.sleep(1.1)  # tokens carry second-precision issue times

    r = client.post(
        "/api/v1/auth/reset-password",
        # Any case/spacing of the code and any common number format are accepted.
        json={
            "mobile": "+91 98765-43210",
            "recovery_code": code.lower().replace("-", " "),
            "new_password": "second-password",
        },
    )
    assert r.status_code == 200, r.text
    new_code = r.json()["recovery_code"]
    assert new_code != code

    assert login(client).status_code == 401
    assert login(client, password="second-password").status_code == 200
    # Older sessions are signed out; the token from the reset works.
    assert client.get("/api/v1/budgets", headers=bearer(old_token)).status_code == 401
    assert client.get("/api/v1/budgets", headers=bearer(r.json()["access_token"])).status_code == 200

    # The code is single-use.
    again = client.post(
        "/api/v1/auth/reset-password",
        json={"mobile": "9876543210", "recovery_code": code, "new_password": "third-password"},
    )
    assert again.status_code == 400


def test_wrong_code_or_unknown_user_look_the_same(client):
    register(client)
    bad = {"recovery_code": "AAAA-BBBB-CCCC-DDDD", "new_password": "whatever-123"}
    wrong = client.post("/api/v1/auth/reset-password", json={"mobile": "9876543210", **bad})
    unknown = client.post("/api/v1/auth/reset-password", json={"mobile": "9123456789", **bad})
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json()
    assert login(client).status_code == 200  # password unchanged


def test_change_password_signs_out_other_sessions(client):
    register(client)
    other_device = login(client).json()["access_token"]
    this_device = login(client).json()["access_token"]
    time.sleep(1.1)

    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "nope", "new_password": "second-password"},
        headers=bearer(this_device),
    )
    assert wrong.status_code == 400

    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "first-password", "new_password": "second-password"},
        headers=bearer(this_device),
    )
    assert r.status_code == 200
    assert client.get("/api/v1/budgets", headers=bearer(other_device)).status_code == 401
    assert client.get("/api/v1/budgets", headers=bearer(r.json()["access_token"])).status_code == 200
    assert login(client, password="second-password").status_code == 200


def test_new_recovery_code_needs_password_and_replaces_old(client):
    first = register(client)["recovery_code"]
    token = login(client).json()["access_token"]
    assert (
        client.post("/api/v1/auth/recovery-code", json={"password": "nope"}, headers=bearer(token)).status_code == 400
    )
    r = client.post("/api/v1/auth/recovery-code", json={"password": "first-password"}, headers=bearer(token))
    assert r.status_code == 200
    second = r.json()["recovery_code"]
    old = client.post(
        "/api/v1/auth/reset-password", json={"mobile": "9876543210", "recovery_code": first, "new_password": "x" * 10}
    )
    assert old.status_code == 400
    ok = client.post(
        "/api/v1/auth/reset-password", json={"mobile": "9876543210", "recovery_code": second, "new_password": "y" * 10}
    )
    assert ok.status_code == 200


def test_weak_new_password_rejected(client):
    code = register(client)["recovery_code"]
    r = client.post(
        "/api/v1/auth/reset-password", json={"mobile": "9876543210", "recovery_code": code, "new_password": "short"}
    )
    assert r.status_code == 422
