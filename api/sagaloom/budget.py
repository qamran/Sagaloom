"""The monthly AI budget (M5 spec §5.5a): one app-wide amount in US$ per account per calendar
month (UTC), `monthly_budget_usd` in developer settings. The admin has no limit."""

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from sagaloom.models import User
from sagaloom.promptlog import next_month_start

OVER_BUDGET = "You've used this month's AI budget (${budget:.2f}). It resets on {reset}."


def budget_reset_date(now: datetime) -> date:
    """The day the budget of `now`'s month resets: the first of the next month (UTC)."""
    return next_month_start(now).date()


def check_budget(deps: Any, user: User, now: datetime | None = None) -> None:
    """402 when `user` (not the admin) has spent this month's budget or more; a budget of 0
    blocks every AI action. Called before a new turn, a resumed graph or an import starts, so a
    turn already running finishes even if it crosses the line. `now` defaults to `deps.now()`,
    the clock the prompt records are stamped with."""
    if user.is_admin:
        return
    now = now or deps.now()
    budget = deps.dev_settings.get().monthly_budget_usd
    if deps.promptlog.month_spend(user.id, now) >= budget:
        raise HTTPException(
            status_code=402,
            detail=OVER_BUDGET.format(budget=budget, reset=budget_reset_date(now).isoformat()),
        )
