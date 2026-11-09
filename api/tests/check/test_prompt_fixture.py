"""Pins the judge prompt format the web drawer masks (web/lib/maskSecrets.ts).

`web/tests/fixtures/judge-prompt.txt` is real `_build_prompt` output for an update of the Mayor
(`ent_0003`, Age 54 -> 60, its secret fact told by Ilsa Corran, plus a `Kept in` fact that pairs
with the secret ent_0019 in Pass 1) with related entries ent_0002, ent_0003 and ent_0019. It so
pins every secret format the mask relies on: `[secret]`, `[secret] (told by …)`,
`(entry status: secret)` and `Entry status: secret`. The web tests mask it, so a change to `_build_prompt`, `_render` or `_fact_line` that would let a secret
slip past the mask fails here first.

To regenerate after an intended prompt change (then rerun the web tests and commit the file):

    cd api && SAGALOOM_REGEN_FIXTURES=1 uv run pytest -q tests/check/test_prompt_fixture.py
"""

import os
from pathlib import Path

import pytest

from sagaloom.check.contradiction import _build_prompt
from sagaloom.models import EntryDraft, Fact, Proposal
from sagaloom.seed import _seed_entries

ROOT = Path(__file__).resolve().parents[3]
SEED = ROOT / "seed" / "velmar"
FIXTURE = ROOT / "web" / "tests" / "fixtures" / "judge-prompt.txt"
REGEN = "SAGALOOM_REGEN_FIXTURES"


def _judge_prompt() -> str:
    by_id = {e.id: e for e in _seed_entries(SEED, "velmar")}
    mayor = by_id["ent_0003"]
    facts = [
        f.model_copy(update={"value": "60"})
        if f.key == "Age"
        else f.model_copy(update={"told_by": "Ilsa Corran"})
        if f.status == "secret"
        else f
        for f in mayor.facts
    ]
    facts.append(Fact(key="Kept in", value="A drawer in the Tidehall"))
    draft = EntryDraft(
        title=mayor.title,
        type=mayor.type,
        body=mayor.body,
        status=mayor.status,
        aliases=mayor.aliases,
        facts=facts,
    )
    proposal = Proposal(
        proposal_id="p_fixture",
        action="update",
        world_id="velmar",
        entry_id=mayor.id,
        before=mayor,
        after=draft,
    )
    related = [by_id[i] for i in ("ent_0002", "ent_0003", "ent_0019")]
    return _build_prompt(proposal, draft, related)


def test_judge_prompt_fixture_is_current():
    actual = _judge_prompt()
    if os.environ.get(REGEN) == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        with open(FIXTURE, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(actual)
    hint = f"Regenerate it with {REGEN}=1 (see this test's header), then rerun the web tests."
    if not FIXTURE.exists():
        pytest.fail(f"{FIXTURE} is missing. {hint}")
    expected = FIXTURE.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, f"{FIXTURE} is stale: the judge prompt format changed. {hint}"
