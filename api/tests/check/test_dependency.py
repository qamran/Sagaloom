from pathlib import Path

from sagaloom.check.dependency import dependency_check
from sagaloom.models import Entry, Link, Proposal
from sagaloom.seed import load_seed
from sagaloom.store.worlds import WorldRegistry

SEED = Path(__file__).resolve().parents[3] / "seed" / "velmar"


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


def test_dependency_marks_link_only(store, tmp_path):
    load_seed(store, WorldRegistry(tmp_path / "worlds.json"), SEED)
    choir = store.get_entry("velmar", "ent_0004")
    p = Proposal(
        proposal_id="p1", action="delete", world_id="velmar", entry_id=choir.id, before=choir, after=None
    )
    via = {d.id: d.via for d in dependency_check(store, p).dependents}
    assert via["ent_0003"] == "link"
    assert [i for i, v in via.items() if v == "link"] == ["ent_0003"]
    for i in ["ent_0007", "ent_0011", "ent_0012", "ent_0015", "ent_0016", "ent_0018", "ent_0019"]:
        assert via[i] == "text"


def test_dependency_text_mention_first(store):
    ister = store.upsert_entry(mk("ent_0001", "Ister"))
    linked = mk("ent_0002", "Velmar", "Quiet.").model_copy(
        update={"links": [Link(target_id="ent_0001", relation="lit by")]}
    )
    store.upsert_entry(linked)
    store.upsert_entry(mk("ent_0003", "Harbour", "Under Ister at night."))
    res = dependency_check(store, prop(ister))
    assert [(d.id, d.via) for d in res.dependents] == [("ent_0003", "text"), ("ent_0002", "link")]
