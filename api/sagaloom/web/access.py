"""`current_user`: the verified Clerk user behind a request (M5, spec §5.1)."""

import logging

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from sagaloom.accounts import ensure_user
from sagaloom.auth import AuthError, Claims
from sagaloom.models import User

log = logging.getLogger(__name__)

SIGN_IN_REQUIRED = "sign in required"


def bearer_token(authorization: str | None) -> str | None:
    """The token of an `Authorization: Bearer <token>` header, else None."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


class UnconfiguredVerifier:
    """Used when `CLERK_ISSUER` is unset: nobody can sign in."""

    def verify(self, token: str) -> Claims:
        raise AuthError("CLERK_ISSUER is not set")


async def current_user(request: Request) -> User:
    """Verifies the bearer token and returns its user, also stored on `request.state.user`.
    401 `sign in required` for a missing or untrusted token; neither the token nor the
    verifier's reason is logged or returned."""
    token = bearer_token(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED)
    deps = request.app.state.deps
    try:
        # A JWKS cache miss fetches Clerk's keys: keep that off the event loop.
        claims = await run_in_threadpool(deps.verifier.verify, token)
    except AuthError:
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED) from None
    try:
        user = await ensure_user(deps, claims)
    except AuthError:
        # The token is good but the Clerk profile lookup failed: not the user's fault.
        log.warning("Clerk profile lookup failed for a signed-in user")
        raise HTTPException(status_code=503, detail="account service unavailable") from None
    request.state.user = user
    return user


def user_of(request: Request) -> User:
    """The user `current_user` stored for this request."""
    return request.state.user
