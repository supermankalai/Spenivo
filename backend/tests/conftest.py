import os
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-only-secret-" + "x" * 40)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402

from app.api.deps import get_google_verifier  # noqa: E402
from app.core.google import GoogleIdentity, InvalidGoogleToken  # noqa: E402
from app.db import set_engine  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    """
    Fresh database per test, built by running the real Alembic migrations.
    Uses SQLite by default; set TEST_DATABASE_URL to run against PostgreSQL
    (the database is emptied with a downgrade afterwards).
    """
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys = ON")

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    set_engine(engine)

    from app.main import app

    app.dependency_overrides[get_google_verifier] = lambda: fake_google_verify
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

    if engine.dialect.name != "sqlite":
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, "base")
    engine.dispose()


def fake_google_token(sub: str, email: str | None = None, name: str | None = None) -> str:
    """Stands in for a Google ID token; real signature checks are in test_google_token.py."""
    return f"fake-google-token|{sub}|{email or ''}|{name or ''}"


def fake_google_verify(token: str) -> GoogleIdentity:
    parts = token.split("|")
    if len(parts) != 4 or parts[0] != "fake-google-token":
        raise InvalidGoogleToken("That Google sign-in didn’t work. Please try again.")
    return GoogleIdentity(sub=parts[1], email=parts[2] or None, name=parts[3] or None)


def auth_headers(client: TestClient, sub: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/google", json={"id_token": fake_google_token(sub, f"{sub}@gmail.com")})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def alice(client):
    return auth_headers(client, "google-alice-0001")


@pytest.fixture
def bob(client):
    return auth_headers(client, "google-bob-0002")


def make_tx(**overrides):
    base = {
        "amount_minor_units": 25000,
        "category_id": "food",
        "merchant": "Swiggy",
        "payment_method": "UPI",
        "transaction_datetime": 1_741_766_400_000,
    }
    base.update(overrides)
    return base
