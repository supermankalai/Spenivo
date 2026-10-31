"""The real Google ID token checks, with a locally generated RSA key standing in for Google's."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.google import InvalidGoogleToken, verify_google_id_token

CLIENT_ID = "1234-web.apps.googleusercontent.com"
_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(signing_key=_key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "110169484474386276334",
        "email": "asha@gmail.com",
        "email_verified": True,
        "name": "Asha",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, signing_key, algorithm="RS256")


def verify(token: str, audiences=(CLIENT_ID,)):
    return verify_google_id_token(token, list(audiences), key_for=lambda _t: _key.public_key())


def test_valid_token():
    identity = verify(_token())
    assert identity.sub == "110169484474386276334"
    assert identity.email == "asha@gmail.com"
    assert identity.name == "Asha"


def test_unverified_email_is_dropped_but_sign_in_works():
    assert verify(_token(email_verified=False)).email is None


@pytest.mark.parametrize(
    "token",
    [
        _token(aud="someone-elses-app.apps.googleusercontent.com"),
        _token(iss="https://evil.example.com"),
        _token(exp=int(time.time()) - 3600, iat=int(time.time()) - 7200),
        _token(signing_key=_other_key),
        _token(sub=None),
        "not.a.jwt",
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "bad-signature", "no-subject", "garbage"],
)
def test_rejected(token):
    with pytest.raises(InvalidGoogleToken):
        verify(token)


def test_unconfigured_server_rejects_everything():
    with pytest.raises(InvalidGoogleToken, match="not configured"):
        verify(_token(), audiences=())
