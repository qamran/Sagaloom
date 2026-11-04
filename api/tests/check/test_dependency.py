from sagaloom.check.dependency import dependency_check
from sagaloom.models import Entry, Proposal


def mk(id, title, body="x"):
    return Entry(id=id, world_id="w1", title=title, type="place", body=body)


def prop(before):
    return Proposal(proposal_id="p1", action="delete", world_id="w1", entry_id=before.id, before=before, after=None)


def test_dependency_check_lists_two_mentioning_entries(store):
    ister = store.upsert_entry(mk("ent_0001", "Ister"))
    store.upsert_entry(mk("ent_0002", "Velmar", "Lit by Ister."))
    store.upsert_entry(mk("ent_0003", "Harbour", "Under Ister at night."))
    store.upsert_entry(mk("ent_0004", "Other", "Nothing."))
    res = dependency_check(store, prop(ister))
    assert res.verdict == "none" and res.flags == [] and res.proposal_id == "p1"
    assert [d.id for d in res.dependents] == ["ent_0002", "ent_0003"]


def test_dependency_check_no_mentions_returns_empty(store):
    ister = store.upsert_entry(mk("ent_0001", "Ister"))
    store.upsert_entry(mk("ent_0002", "Velmar", "Quiet."))
    p = prop(ister).model_copy(update={"before": None})
    assert dependency_check(store, p).dependents == []
