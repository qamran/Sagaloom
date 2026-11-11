"""The signed-in user's account row (M5, spec §5.4). Task 5 adds provisioning on top."""

from typing import Any

from sagaloom.auth import AuthError, Claims
from sagaloom.models import User
from sagaloom.store.users import admin_flag


async def ensure_user(deps: Any, claims: Claims) -> User:
    """The user for verified `claims`, created from their Clerk profile on first sight. Holds the
    user's lock so concurrent first requests fetch and insert once. `deps` is the app's `AppDeps`."""
    async with deps.user_locks.hold(claims.sub):
        user = deps.users.get(claims.sub)
        if user is None:
            if deps.directory is None:
                raise AuthError("CLERK_SECRET_KEY is not set")
            profile = await deps.directory.fetch(claims.sub)
            user = deps.users.upsert_profile(
                claims.sub,
                email=profile.email,
                email_verified=profile.email_verified,
                display_name=profile.display_name,
            )
    return user.model_copy(update={"is_admin": admin_flag(user, deps.settings.admin_email)})
