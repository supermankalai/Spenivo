from datetime import UTC
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, token_issued_at
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The ONLY source of user identity. Never trust a user id from a request body."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    # A password change or reset signs out every token issued before it.
    if user.password_changed_at is not None:
        changed = user.password_changed_at
        if changed.tzinfo is None:  # SQLite returns naive UTC datetimes
            changed = changed.replace(tzinfo=UTC)
        issued = token_issued_at(credentials.credentials)
        if issued is None or issued < int(changed.timestamp()):
            raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
