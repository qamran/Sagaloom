import pytest

from sagaloom.check.badge import BADGE_ORDER, badge_of, with_badges, worst_badge
from sagaloom.models import CheckResult, Flag


def flag(kind, severity=None):
    return Flag(kind=kind, entry_id="ent_0001", title="T", severity=severity, explanation="x")


@pytest.mark.parametrize(
    ("verdict", "flags", "badge"),
    [
        ("failed", [flag("conflict", "hard")], "failed"),
        ("conflict", [flag("note", "note"), flag("conflict", "hard")], "conflict"),
        ("possible", [flag("retcon"), flag("conflict", "possible")], "possible"),
        ("none", [flag("note", "note"), flag("retcon")], "retcon"),
        ("none", [flag("note", "note")], "note"),
        ("none", [], "clear"),
    ],
)
def test_badge_precedence(verdict, flags, badge):
    assert badge_of(CheckResult(proposal_id="p1", verdict=verdict, flags=flags)) == badge


def test_badge_order():
    assert BADGE_ORDER == ("conflict", "failed", "possible", "retcon", "note", "clear")


def test_worst_badge():
    assert worst_badge([]) is None
    assert worst_badge(["note", "possible"]) == "possible"
    assert worst_badge(iter(["clear", "failed", "conflict"])) == "conflict"


def test_with_badges_copies_and_adds_a_badge_per_check():
    check = CheckResult(proposal_id="p1", verdict="none", flags=[flag("retcon")]).model_dump(mode="json")
    value = {"proposals": [{"proposal_id": "p1"}], "checks": {"p1": check}, "error": "bad"}
    out = with_badges(value)
    assert out["checks"]["p1"]["badge"] == "retcon"
    assert out["error"] == "bad" and out["proposals"] == value["proposals"]
    assert "badge" not in value["checks"]["p1"]
