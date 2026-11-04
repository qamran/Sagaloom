from sagaloom.check.myth import apply_save_as_myth
from sagaloom.models import CheckResult, Entry, EntryDraft, Fact, Flag, Proposal

BEFORE = Entry(
    id="ent_0001", world_id="w1", title="Ister", type="place", body="Old body.",
    facts=[Fact(key="Moons", value="One (Ister)"), Fact(key="Tide", value="High")],
)
AFTER = EntryDraft(
    title="Ister", type="place", body="New body.",
    facts=[Fact(key="Moons", value="Three"), Fact(key="Tide", value="Low")],
)
RESULT = CheckResult(
    proposal_id="p1", verdict="conflict",
    flags=[Flag(kind="retcon", entry_id="ent_0001", title="Ister", fact_key="moons", explanation="x"),
           Flag(kind="note", entry_id="ent_0001", title="Ister", fact_key="Tide", explanation="y")],
)


def prop(action, before):
    return Proposal(proposal_id="p1", action=action, world_id="w1", entry_id=before and before.id, before=before, after=AFTER)


def test_save_as_myth_keeps_canon_and_adds_myth_fact():
    out = apply_save_as_myth(prop("update", BEFORE), RESULT, "ent_0009")
    got = [(f.key, f.value, f.status, f.told_by) for f in out.facts]
    assert got == [
        ("Moons", "One (Ister)", "canon", None),
        ("Moons", "Three", "myth", "ent_0009"),
        ("Tide", "Low", "canon", None),
    ]
    assert AFTER.facts[0].status == "canon"  # input not mutated


def test_save_as_myth_on_update_restores_before_body():
    assert apply_save_as_myth(prop("update", BEFORE), RESULT, None).body == "Old body."


def test_save_as_myth_on_create_marks_myth_only():
    out = apply_save_as_myth(prop("create", None), RESULT, "ent_0009")
    assert out.body == "New body."
    assert [(f.value, f.status) for f in out.facts] == [("Three", "myth"), ("Low", "canon")]
