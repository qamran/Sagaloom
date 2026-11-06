"""Review badges (spec §3.8): derived from a check result at the API edge, never stored, so a
checkpoint written before badges existed still shows them."""

from collections.abc import Iterable
from typing import Literal

from sagaloom.models import CheckResult

Badge = Literal["conflict", "failed", "possible", "retcon", "note", "clear"]
BADGE_ORDER: tuple[Badge, ...] = ("conflict", "failed", "possible", "retcon", "note", "clear")


def badge_of(result: CheckResult) -> Badge:
    if result.verdict == "failed":
        return "failed"
    conflicts = [f for f in result.flags if f.kind == "conflict"]
    if any(f.severity == "hard" for f in conflicts):
        return "conflict"
    if conflicts:
        return "possible"
    if any(f.kind == "retcon" for f in result.flags):
        return "retcon"
    return "note" if result.flags else "clear"


def worst_badge(badges: Iterable[Badge]) -> Badge | None:
    """The earliest of `badges` in BADGE_ORDER; None when there are none."""
    return min(badges, key=BADGE_ORDER.index, default=None)


def with_badges(value: dict) -> dict:
    """A copy of an interrupt payload whose every check gains its `badge`."""
    checks = value.get("checks") or {}
    return {
        **value,
        "checks": {
            pid: {**check, "badge": badge_of(CheckResult.model_validate(check))}
            for pid, check in checks.items()
        },
    }
