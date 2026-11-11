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
        # The `iss` claim has no trailing slash; an issuer configured with one must still match.
        self._issuer = issuer.rstrip("/")
        self._web_origin = web_origin
        # PyJWKClient does no network I/O until the first verify(); it caches the keys.
        self._jwks = jwks_client or jwt.PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json", cache_keys=True, timeout=5
        )

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
        except httpx.HTTPStatusError as exc:
            # The status only: the body may echo request details. Not `from exc` (see below).
            raise AuthError(f"Clerk lookup failed: HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, ValueError) as exc:
            # Not `from exc`: the chained request/response text must not reach logs.
            raise AuthError(f"Clerk lookup failed: {type(exc).__name__}") from None
        return _profile(body)


def _profile(body: object) -> ClerkProfile:
    """The profile in a Clerk user object; any unexpected shape is an `AuthError`."""
    if not isinstance(body, dict):
        raise AuthError("Clerk user is malformed")
    primary = body.get("primary_email_address_id")
    addresses = body.get("email_addresses")
    if not isinstance(addresses, list):
        raise AuthError("Clerk user is malformed")
    match = next((e for e in addresses if isinstance(e, dict) and e.get("id") == primary), None)
    if match is None:
        raise AuthError("Clerk user has no primary email")
    email = match.get("email_address")
    if not isinstance(email, str) or not email:
        raise AuthError("Clerk user is malformed")
    verification = match.get("verification")
    verified = isinstance(verification, dict) and verification.get("status") == "verified"
    first, last = body.get("first_name"), body.get("last_name")
    name = " ".join(n for n in (first, last) if isinstance(n, str) and n).strip()
    return ClerkProfile(email=email, email_verified=verified, display_name=name or email.split("@")[0])
