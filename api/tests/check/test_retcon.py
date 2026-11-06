from sagaloom.check.retcon import detect_retcons
from sagaloom.models import Entry, EntryDraft, Fact


def mk(facts, body="A moon."):
    return Entry(id="ent_0001", world_id="w1", title="Ister", type="place", body=body, facts=facts)


def draft(facts, body="A moon."):
    return EntryDraft(title="Ister", type="place", body=body, facts=facts)


def test_changed_canon_fact_is_retcon():
    flags = detect_retcons(
        mk([Fact(key="Moons", value="One (Ister)")]), draft([Fact(key="moons", value="Three")])
    )
    assert len(flags) == 1
    f = flags[0]
    assert (f.kind, f.entry_id, f.title, f.fact_key) == ("retcon", "ent_0001", "Ister", "Moons")
    assert (f.existing_fact, f.new_fact, f.severity) == ("One (Ister)", "Three", None)
    assert f.explanation == "Changes established canon: One (Ister) → Three"


def test_removed_canon_fact_is_retcon():
    flags = detect_retcons(mk([Fact(key="Moons", value="One")]), draft([]))
    assert len(flags) == 1 and flags[0].new_fact is None


def test_prose_only_edit_has_no_retcon():
    facts = [Fact(key="Moons", value="One")]
    assert detect_retcons(mk(facts), draft([Fact(key=" MOONS ", value=" one ")], body="New prose.")) == []


def test_myth_fact_change_is_not_retcon():
    assert detect_retcons(mk([Fact(key="Moons", value="One", status="myth")]), draft([Fact(key="Moons", value="Three")])) == []


def test_secret_fact_change_is_retcon():
    flags = detect_retcons(mk([Fact(key="Vault", value="Empty", status="secret")]), draft([Fact(key="Vault", value="Full", status="secret")]))
    assert len(flags) == 1
    assert flags[0].existing_secret is True


def test_canon_fact_retcon_is_not_secret_but_secret_entry_is():
    changed = draft([Fact(key="Moons", value="Three")])
    assert detect_retcons(mk([Fact(key="Moons", value="One")]), changed)[0].existing_secret is False
    hidden = mk([Fact(key="Moons", value="One")]).model_copy(update={"status": "secret"})
    assert detect_retcons(hidden, changed)[0].existing_secret is True


def test_one_retcon_flag_per_stored_fact():
    before = mk([Fact(key="Members", value="About sixty"), Fact(key="Members", value="Ashen Choir", status="secret")])
    flags = detect_retcons(before, draft([Fact(key="Members", value="About seventy")]))
    assert [(f.existing_fact, f.existing_secret) for f in flags] == [
        ("About sixty", False),
        ("Ashen Choir", True),
    ]
    assert all(f.new_fact == "About seventy" and f.fact_key == "Members" for f in flags)
    assert flags[0].explanation == "Changes established canon: About sixty → About seventy"


def test_retcon_pure_addition():
    flags = detect_retcons(
        mk([Fact(key="Moons", value="One (Ister)")]),
        draft([Fact(key="Moons", value="One (Ister)"), Fact(key="Moons", value="Three")]),
    )
    assert len(flags) == 1
    f = flags[0]
    assert (f.existing_fact, f.new_fact) == ("One (Ister)", "Three")
    assert f.explanation.startswith("Adds to established canon")
    assert f.explanation == "Adds to established canon: Three"
    assert f.existing_secret is False


def test_removed_fact_explanation_names_one_fact():
    flags = detect_retcons(mk([Fact(key="Moons", value="One"), Fact(key="Moons", value="Ister")]), draft([]))
    assert [f.explanation for f in flags] == [
        "Removes established canon: One",
        "Removes established canon: Ister",
    ]
