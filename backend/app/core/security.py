import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: str, now: datetime | None = None) -> str:
    settings = get_settings()
    issued = now or datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# No 0/O or 1/I/L: easy to read back and type. 31 symbols ^ 16 ≈ 2^79 — not guessable.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_recovery_code() -> str:
    """A one-time account recovery code like K7QM-2XWD-9TFA-HR4P (shown to the user once)."""
    chars = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(chars[i : i + 4] for i in range(0, 16, 4))


def normalise_recovery_code(code: str) -> str:
    """Accept any case, spaces or dashes; hash and compare the bare 16 characters."""
    return "".join(c for c in code.upper() if c.isalnum())


def hash_recovery_code(code: str) -> str:
    return _hasher.hash(normalise_recovery_code(code))


def verify_recovery_code(code: str, code_hash: str) -> bool:
    return _hasher.verify(normalise_recovery_code(code), code_hash)


def token_issued_at(token: str) -> int | None:
    """`iat` (seconds) of a token already validated by decode_access_token."""
    try:
        iat = jwt.decode(token, options={"verify_signature": False}).get("iat")
    except jwt.PyJWTError:
        return None
    return iat if isinstance(iat, int) else None


def decode_access_token(token: str) -> str | None:
    """Return the user id for a valid token, else None."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None
