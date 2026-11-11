"""The signed-in user's account: profile, admin and their own Velmar (M5, spec §5.4)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sagaloom.auth import AuthError, Claims
from sagaloom.models import User
from sagaloom.seed import copy_velmar
from sagaloom.store.users import admin_flag

log = logging.getLogger(__name__)

# Clerk is the authority for identity: a stored profile is re-checked this often. An unverified
# email soon (so a newly verified admin is recognised), a verified one daily (so an address that
# moved away from ADMIN_EMAIL loses admin).
RECHECK_UNVERIFIED = timedelta(minutes=10)
RECHECK_VERIFIED = timedelta(hours=24)
# After a failed refresh the stored profile is used this long before Clerk is tried again, so an
# outage (a hanging Clerk) does not stall every request. `profile_checked_at` is not moved.
RETRY_AFTER_FAILURE = timedelta(seconds=60)

# Provisioning tasks outlive a cancelled request (see `ensure_user`); held here so they are not
# garbage-collected while running.
_running: set[asyncio.Task] = set()


def _done(task: asyncio.Task) -> None:
    _running.discard(task)
    # Mark the outcome retrieved: the request awaiting it re-raises it; one that was cancelled
    # has gone, and the next request retries the provisioning.
    if not task.cancelled():
        task.exception()


def _refresh_due(deps: Any, user: User, now: datetime) -> bool:
    failed = deps.refresh_failures.get(user.id)
    if failed is not None and now - failed < RETRY_AFTER_FAILURE:
        return False
    checked = datetime.fromisoformat(user.profile_checked_at)
    if checked.tzinfo is None:  # a hand-written or older row: stored times are UTC
        checked = checked.replace(tzinfo=UTC)
    every = RECHECK_VERIFIED if user.email_verified else RECHECK_UNVERIFIED
    return now - checked >= every


def _is_admin(deps: Any, user: User) -> bool:
    return admin_flag(user, deps.settings.admin_email)


def _settled(deps: Any, user: User | None, now: datetime) -> bool:
    """Nothing to do for this user: known, profile fresh, owns a world, and (for the admin) no
    ownerless world left to take."""
    if user is None or _refresh_due(deps, user, now):
        return False
    worlds = deps.worlds.all_worlds()
    if _is_admin(deps, user) and any(w.owner_id is None for w in worlds):
        return False
    return deps.seed_dir is None or any(w.owner_id == user.id for w in worlds)


async def _profile(deps: Any, sub: str, user: User | None, now: datetime) -> User:
    """`user` with its profile fetched from Clerk. A new user needs Clerk (`AuthError` if it
    fails); a known user keeps the stored profile when the refresh fails."""
    try:
        if deps.directory is None:
            raise AuthError("CLERK_SECRET_KEY is not set")
        profile = await deps.directory.fetch(sub)
    except AuthError as exc:
        if user is None:
            raise
        log.warning("Clerk profile refresh failed; keeping the stored profile: %s", exc)
        deps.refresh_failures[sub] = now
        return user
    deps.refresh_failures.pop(sub, None)
    return deps.users.upsert_profile(
        sub,
        email=profile.email,
        email_verified=profile.email_verified,
        display_name=profile.display_name,
        checked_at=now,
    )


async def _provision(deps: Any, sub: str) -> User:
    """The locked part of `ensure_user`: re-read, refresh, admin assignment, Velmar copy."""
    async with deps.user_locks.hold(sub):
        now = deps.now()
        user = deps.users.get(sub)
        if user is None or _refresh_due(deps, user, now):
            user = await _profile(deps, sub, user, now)
        if _is_admin(deps, user):
            await asyncio.to_thread(deps.worlds.assign_unowned, user.id)
        if deps.seed_dir is not None and not deps.worlds.owned_by(user.id):
            # 19 embedding calls: keep them off the event loop.
            world = await asyncio.to_thread(copy_velmar, deps.store, deps.worlds, deps.seed_dir, user.id)
            deps.users.set_last_world(user.id, world.id)
            user = user.model_copy(update={"last_world_id": world.id})
        return user


async def ensure_user(deps: Any, claims: Claims) -> User:
    """The user for verified `claims`, with `is_admin` computed from the stored profile.

    A settled user (see `_settled`) is read without a lock. Otherwise, under the user's lock and
    re-reading the row: fetch the profile on first sight or when a re-check is due (a failed
    refresh keeps the stored profile and is not retried for `RETRY_AFTER_FAILURE`); if admin,
    take every ownerless world; if the user then owns no world, copy Velmar for them and make it
    their last world. The locked part runs as its own shielded task, so a cancelled request
    does not release the lock while a copy is still running. `deps` is the app's `AppDeps`;
    `deps.seed_dir` None skips the copy."""
    user = deps.users.get(claims.sub)
    if not _settled(deps, user, deps.now()):
        task = asyncio.create_task(_provision(deps, claims.sub))
        _running.add(task)
        task.add_done_callback(_done)
        user = await asyncio.shield(task)
    assert user is not None
    return user.model_copy(update={"is_admin": _is_admin(deps, user)})
