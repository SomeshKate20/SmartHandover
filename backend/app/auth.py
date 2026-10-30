from dataclasses import dataclass
from functools import lru_cache
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    clerk_id: str


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, timeout=5)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    issuer = os.getenv("CLERK_ISSUER", "").strip().rstrip("/")
    jwks_url = os.getenv("CLERK_JWKS_URL", "").strip()
    authorized_parties = {
        party.strip().rstrip("/")
        for party in os.getenv("CLERK_AUTHORIZED_PARTIES", "").split(",")
        if party.strip()
    }
    if not issuer or not jwks_url or not authorized_parties:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on the backend",
        )

    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider is temporarily unavailable",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        ) from exc

    authorized_party = claims.get("azp")
    if authorized_party is not None and authorized_party not in authorized_parties:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token was issued for an untrusted application",
        )

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication token")
    if claims.get("sts") == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Complete account setup before continuing")

    return AuthenticatedUser(clerk_id=subject)
