"""
Verifies Google ID tokens from Google Sign-In on the phone.

The app sends the ID token Google gave it; we check Google's signature (keys
from Google's JWKS endpoint, cached), issuer, expiry and that the audience is
one of our OAuth client ids. Only then is the Google account id trusted.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import jwt

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class InvalidGoogleToken(Exception):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str | None
    name: str | None


KeyResolver = Callable[[str], object]


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    # Keys are cached in-process; Google rotates them roughly weekly.
    return jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, lifespan=6 * 60 * 60, timeout=10)


def _google_key(token: str) -> object:
    return _jwks_client().get_signing_key_from_jwt(token).key


def verify_google_id_token(token: str, audiences: list[str], key_for: KeyResolver = _google_key) -> GoogleIdentity:
    if not audiences:
        raise InvalidGoogleToken("Google sign-in is not configured on the server.")
    try:
        key = key_for(token)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audiences,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=60,
        )
    except (jwt.PyJWTError, OSError) as e:
        raise InvalidGoogleToken("That Google sign-in didn’t work. Please try again.") from e
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise InvalidGoogleToken("That Google sign-in didn’t work. Please try again.")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidGoogleToken("That Google sign-in didn’t work. Please try again.")
    email = claims.get("email") if claims.get("email_verified") in (True, "true") else None
    name = claims.get("name")
    return GoogleIdentity(
        sub=sub,
        email=email if isinstance(email, str) else None,
        name=name[:120] if isinstance(name, str) else None,
    )
