"""JWT bearer authentication."""
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import settings as S
from . import state

_bearer = HTTPBearer(auto_error=False)
_ALGORITHM = "HS256"


def create_token(username):
    now = int(time.time())
    ttl = S.TOKEN_MINUTES * 60
    token = jwt.encode({"sub": username, "iat": now, "exp": now + ttl}, state.jwt_secret(), algorithm=_ALGORITHM)
    return token, ttl


def _unauthorized(detail="Not authenticated"):
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = jwt.decode(creds.credentials, state.jwt_secret(), algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired, please sign in again")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")
    user = state.get_user(payload.get("sub", ""))
    if user is None:
        raise _unauthorized("Unknown user")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user
