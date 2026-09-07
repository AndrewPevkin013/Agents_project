import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    secret_key = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    if not secret_key:
        raise RuntimeError(
            "JWT_SECRET_KEY is not configured"
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=[algorithm],
        )

        if payload.get("type") != "access":
            raise jwt.InvalidTokenError(
                "Wrong token type"
            )

        if not payload.get("sub"):
            raise jwt.InvalidTokenError(
                "Missing subject"
            )

        return payload

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )


def require_role(*roles: str):

    def dependency(
        user: dict = Depends(get_current_user),
    ) -> dict:

        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return dependency