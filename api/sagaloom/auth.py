"""Clerk session-token verification and the Clerk profile lookup (M5, spec §5.1)."""

from typing import Protocol

import httpx
import jwt
from pydantic import BaseModel

CLERK_API = "https://api.clerk.com/v1"


class AuthError(Exception):
    """The token or the Clerk lookup could not be trusted. Never carries a token or key."""


class AuthUnavailable(AuthError):
    """Clerk could not be reached to check the token (its keys did not load): not the user's fault."""


class Claims(BaseModel):
    sub: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Claims: ...


class ClerkVerifier:
    def __init__(self, issuer: str, web_origin: str, *, jwks_client=None):
        self._issuer = issuer
        self._web_origin = web_origin
        # PyJWKClient does no network I/O until the first verify(); it caches the keys.
        self._jwks = jwks_client or jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)

    def verify(self, token: str) -> Claims:
        try:
            try:
                key = self._jwks.get_signing_key_from_jwt(token).key
            except jwt.PyJWKClientConnectionError:
                # Not the exception text: it carries the fetch error's details.
                raise AuthUnavailable("Clerk keys unreachable: PyJWKClientConnectionError") from None
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=5,
                options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {type(exc).__name__}") from None
        azp = payload.get("azp")
        if azp is not None and azp != self._web_origin:
            raise AuthError("invalid token: azp")
        return Claims(sub=payload["sub"])


class ClerkProfile(BaseModel):
    email: str
    email_verified: bool
    display_name: str


class ProfileDirectory(Protocol):
    async def fetch(self, user_id: str) -> ClerkProfile: ...


class ClerkDirectory:
    def __init__(self, secret_key: str, http: httpx.AsyncClient | None = None):
        self._secret = secret_key
        self._http = http or httpx.AsyncClient(timeout=10)

    async def fetch(self, user_id: str) -> ClerkProfile:
        try:
            r = await self._http.get(
                f"{CLERK_API}/users/{user_id}", headers={"Authorization": f"Bearer {self._secret}"}
            )
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Not `from exc`: the chained request/response text must not reach logs.
            raise AuthError(f"Clerk lookup failed: {type(exc).__name__}") from None
        primary = body.get("primary_email_address_id")
        match = next((e for e in body.get("email_addresses") or [] if e.get("id") == primary), None)
        if match is None:
            raise AuthError("Clerk user has no primary email")
        email = match["email_address"]
        verified = (match.get("verification") or {}).get("status") == "verified"
        name = f"{body.get('first_name') or ''} {body.get('last_name') or ''}".strip()
        return ClerkProfile(email=email, email_verified=verified, display_name=name or email.split("@")[0])
