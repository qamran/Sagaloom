"""`current_user`: the verified Clerk user behind a request (M5, spec §5.1), and what that user
may reach (spec §5.2): `world_for`, `thread_for`, `require_admin`."""

import logging

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from sagaloom.accounts import ensure_user
from sagaloom.auth import AuthError, AuthUnavailable, Claims
from sagaloom.models import User, World
from sagaloom.store.threads import ThreadInfo

log = logging.getLogger(__name__)

SIGN_IN_REQUIRED = "sign in required"
UNAVAILABLE = "account service unavailable"
WORLD_NOT_FOUND = "world not found"
THREAD_NOT_FOUND = "thread not found"
ADMIN_ONLY = "Only the admin can change developer settings."


def bearer_token(authorization: str | None) -> str | None:
    """The token of an `Authorization: Bearer <token>` header, else None."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    return token if scheme.lower() == "bearer" and token else None


class UnconfiguredVerifier:
    """Used when `CLERK_ISSUER` is unset: nobody can sign in, and that is the server's fault (503)."""

    def verify(self, token: str) -> Claims:
        raise AuthUnavailable("CLERK_ISSUER is not set")


async def current_user(request: Request) -> User:
    """Verifies the bearer token and returns its user, also stored on `request.state.user`.
    401 `sign in required` for a missing or untrusted token; the verifier's reason is logged at
    INFO, the token never. 503 when the token cannot be checked or the profile not fetched."""
    token = bearer_token(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED)
    deps = request.app.state.deps
    try:
        # A JWKS cache miss fetches Clerk's keys: keep that off the event loop.
        claims = await run_in_threadpool(deps.verifier.verify, token)
    except AuthUnavailable as exc:
        # `AuthError` messages carry no token or key, so the reason is safe to log.
        log.warning("Clerk token check unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
    except AuthError as exc:
        log.info("sign-in rejected: %s", exc)  # an exception class name, never the token
        raise HTTPException(status_code=401, detail=SIGN_IN_REQUIRED) from None
    try:
        user = await ensure_user(deps, claims)
    except AuthError as exc:
        # The token is good but the Clerk profile lookup failed: not the user's fault.
        log.warning("Clerk profile lookup failed for a signed-in user: %s", exc)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
    request.state.user = user
    return user


def user_of(request: Request) -> User:
    """The user `current_user` stored for this request."""
    return request.state.user


def can_access_world(user: User, world: World) -> bool:
    """The one ownership rule (spec §5.2). Fails closed: an ownerless world is nobody's, and the
    admin is not exempt (sharing is a later milestone)."""
    return world.owner_id is not None and world.owner_id == user.id


def world_for(request: Request, world_id: str) -> World:
    """The signed-in user's world `world_id`; 404 when it does not exist or is not theirs, so
    ids cannot be probed. Call it before any other check or side effect of the route."""
    world = request.app.state.deps.worlds.get(world_id)
    if world is None or not can_access_world(user_of(request), world):
        raise HTTPException(status_code=404, detail=WORLD_NOT_FOUND)
    return world


def thread_for(request: Request, thread_id: str) -> ThreadInfo:
    """The thread `thread_id` if it lies in one of the signed-in user's worlds, else 404 (also
    when its world is gone). Call it before any other check or side effect of the route."""
    deps = request.app.state.deps
    info = deps.threads.get(thread_id)
    world = deps.worlds.get(info.world_id) if info is not None else None
    if world is None or not can_access_world(user_of(request), world):
        raise HTTPException(status_code=404, detail=THREAD_NOT_FOUND)
    return info


def require_admin(request: Request) -> User:
    """The signed-in user if they are the admin (`ADMIN_EMAIL`, spec §5.5), else 403."""
    user = user_of(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail=ADMIN_ONLY)
    return user
