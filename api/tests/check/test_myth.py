from sagaloom.check.myth import apply_save_as_myth
from sagaloom.check.retcon import detect_retcons
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


MOONS = Entry(
    id="ent_0007", world_id="w1", title="Sky of Velmar", type="place", body="One moon.",
    facts=[Fact(key="Moons", value="One (Ister)")],
)


def renamed(after_facts, flags):
    p = Proposal(
        proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=MOONS,
        after=EntryDraft(title="Sky of Velmar", type="place", body="Three moons.", facts=after_facts),
    )
    return apply_save_as_myth(p, CheckResult(proposal_id="p1", verdict="none", flags=flags), "Old sailors")


def test_save_as_myth_renamed_key():
    removed = Flag(
        kind="retcon", entry_id="ent_0007", title="Sky of Velmar", fact_key="Moons",
        existing_fact="One (Ister)", new_fact=None, explanation="Removes established canon: One (Ister)",
    )
    out = renamed([Fact(key="Number of moons", value="Three")], [removed])
    assert [(f.key, f.value, f.status, f.told_by) for f in out.facts] == [
        ("Number of moons", "Three", "myth", "Old sailors"),
        ("Moons", "One (Ister)", "canon", None),
    ]


# A conflict flag with fact_key=None reaches the new quote rule; the judge's own flags carry the
# proposed key, which today's flagged-key rule already covers.
def test_save_as_myth_renamed_key_by_conflict_new_fact():
    clash = Flag(
        kind="conflict", entry_id="ent_0012", title="Ister", fact_key=None,
        new_fact="Number of moons: Three", severity="hard", explanation="One moon only.",
    )
    out = renamed(
        [Fact(key="Moons", value="One (Ister)"), Fact(key="Number of moons", value="Three")], [clash]
    )
    assert [(f.key, f.status) for f in out.facts] == [("Moons", "canon"), ("Number of moons", "myth")]


def test_save_as_myth_new_unrelated_key_stays_canon():
    clash = Flag(
        kind="conflict", entry_id="ent_0012", title="Ister", fact_key=None,
        new_fact="Number of moons: Three", severity="hard", explanation="One moon only.",
    )
    out = renamed(
        [Fact(key="Moons", value="One (Ister)"), Fact(key="Number of moons", value="Three"),
         Fact(key="Weather", value="Evening sea fog")],
        [clash],
    )
    assert [(f.key, f.status) for f in out.facts] == [
        ("Moons", "canon"), ("Number of moons", "myth"), ("Weather", "canon"),
    ]


def test_save_as_myth_renamed_key_keeps_a_moved_stored_value_canon():
    removed = Flag(
        kind="retcon", entry_id="ent_0007", title="Sky of Velmar", fact_key="Moons",
        existing_fact="One (Ister)", new_fact=None, explanation="Removes established canon: One (Ister)",
    )
    out = renamed([Fact(key="Night sky", value="One (Ister)")], [removed])
    assert [(f.key, f.status) for f in out.facts] == [("Night sky", "canon"), ("Moons", "canon")]


def test_save_as_myth_two_removed_keys_test_the_union_of_their_values():
    before = Entry(
        id="ent_0007", world_id="w1", title="Sky of Velmar", type="place", body="One moon.",
        facts=[Fact(key="Moons", value="One (Ister)"), Fact(key="Tide", value="High")],
    )
    after = EntryDraft(
        title="Sky of Velmar", type="place", body="Three moons.",
        facts=[Fact(key="Night sky", value="One (Ister)"), Fact(key="Number of moons", value="Three")],
    )
    flags = detect_retcons(before, after)
    assert sorted(f.fact_key for f in flags if f.new_fact is None) == ["Moons", "Tide"]
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=before, after=after)
    out = apply_save_as_myth(p, CheckResult(proposal_id="p1", verdict="none", flags=flags), "Old sailors")
    assert [(f.key, f.value, f.status) for f in out.facts] == [
        ("Night sky", "One (Ister)", "canon"),  # moved from Moons: not in Tide's values, still canon
        ("Number of moons", "Three", "myth"),  # a value neither removed key held
        ("Moons", "One (Ister)", "canon"),  # removed keys are restored, as Save as myth keeps canon
        ("Tide", "High", "canon"),
    ]



def test_dropping_one_value_of_a_kept_key_is_not_a_removed_key():
    before = Entry(
        id="ent_0004", world_id="w1", title="The Ashen Choir", type="faction", body="A choir.",
        facts=[Fact(key="Members", value="About sixty"), Fact(key="Members", value="Old guard")],
    )
    after = EntryDraft(
        title="The Ashen Choir", type="faction", body="A choir.",
        facts=[Fact(key="Members", value="About sixty"), Fact(key="Weather", value="Evening sea fog")],
    )
    flags = detect_retcons(before, after)
    assert [f.new_fact for f in flags] == [None]
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0004", before=before, after=after)
    out = apply_save_as_myth(p, CheckResult(proposal_id="p1", verdict="none", flags=flags), "Old sailors")
    assert [(f.key, f.value, f.status) for f in out.facts] == [
        ("Members", "About sixty", "canon"),
        ("Members", "Old guard", "canon"),
        ("Weather", "Evening sea fog", "canon"),
    ]


SKY = Entry(
    id="ent_0007", world_id="w1", title="Sky of Velmar", type="place", body="One moon, Ister.\n",
    facts=[Fact(key="Moons", value="One (Ister)")],
)
SKY_RETCON = CheckResult(
    proposal_id="p1", verdict="conflict",
    flags=[Flag(kind="retcon", entry_id="ent_0007", title="Sky of Velmar", fact_key="Moons", explanation="x")],
)


def test_save_as_myth_keeps_imported_section():
    """An import merge appends the author's passage under its heading: Save as myth keeps it (R3.5),
    while the flagged fact becomes a myth and the stored canon fact is restored."""
    merged = "One moon, Ister.\n\n## Imported from paste (2026-11-06)\n\nThe three moons rose together."
    after = EntryDraft(
        title="Sky of Velmar", type="place", body=merged, trusted=False,
        facts=[Fact(key="Moons", value="Three")],
    )
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=SKY, after=after)
    out = apply_save_as_myth(p, SKY_RETCON, None, imported=True)
    assert out.body == merged
    assert [(f.value, f.status) for f in out.facts] == [("One (Ister)", "canon"), ("Three", "myth")]
    assert out.trusted is False


def test_save_as_myth_restores_body_for_chat_update():
    """A chat update that rewrote the body in place gets the stored body back, as before."""
    after = EntryDraft(
        title="Sky of Velmar", type="place", body="Three moons rise together.",
        facts=[Fact(key="Moons", value="Three")],
    )
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=SKY, after=after)
    assert apply_save_as_myth(p, SKY_RETCON, None, imported=True).body == SKY.body


def test_save_as_myth_restores_body_when_a_heading_follows_a_rewrite():
    """A heading after a changed body is not an import merge: the stored body comes back."""
    after = EntryDraft(
        title="Sky of Velmar", type="place",
        body="Three moons.\n\n## Imported from paste (2026-11-06)\n\nText.",
        facts=[Fact(key="Moons", value="Three")],
    )
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=SKY, after=after)
    assert apply_save_as_myth(p, SKY_RETCON, None, imported=True).body == SKY.body


def test_save_as_myth_restores_body_for_merge_shaped_chat_update():
    """The kept section is a rule about imports, not about a body's shape: a chat update whose
    body looks like an import merge still gets the stored body back on Save as myth."""
    merged = "One moon, Ister.\n\n## Imported from paste (2026-11-06)\n\nThe three moons rose together."
    after = EntryDraft(
        title="Sky of Velmar", type="place", body=merged,
        facts=[Fact(key="Moons", value="Three")],
    )
    p = Proposal(proposal_id="p1", action="update", world_id="w1", entry_id="ent_0007", before=SKY, after=after)
    assert apply_save_as_myth(p, SKY_RETCON, None, imported=False).body == SKY.body
    assert apply_save_as_myth(p, SKY_RETCON, None).body == SKY.body
