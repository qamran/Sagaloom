import json
from pathlib import Path

import pytest

from sagaloom.models import Entry, EntryDraft
from sagaloom.seed import ensure_first_run, load_seed, seed_missing
from sagaloom.store.worlds import WorldRegistry

SEED = Path(__file__).resolve().parents[2] / "seed" / "velmar"


@pytest.fixture
def worlds(tmp_path):
    return WorldRegistry(tmp_path / "worlds.json")


def test_seed_loads_15_to_20_valid_entries(store, worlds):
    n = load_seed(store, worlds, SEED)
    entries = store.list_entries("velmar")
    assert n == len(entries)
    assert 15 <= n <= 20
    for e in entries:
        assert isinstance(e, Entry)
        assert len(e.facts) >= 2, e.title
        assert e.world_id == "velmar"


def test_seed_has_required_entries_and_statuses(store, worlds):
    load_seed(store, worlds, SEED)
    by_id = {e.id: e for e in store.list_entries("velmar")}
    sky = by_id["ent_0007"]
    assert sky.title == "Sky of Velmar" and sky.type == "place"
    facts = {f.key: f.value for f in sky.facts}
    assert facts["Moons"] == "One (Ister)"
    assert facts["At the solstice"] == "Ister rises red"
    assert facts["Weather"] == "Evening sea fog"
    ister = by_id["ent_0012"]
    assert ister.title == "Ister, the red moon" and ister.type == "place"
    assert {f.key: f.value for f in ister.facts}["Only light in the night sky"] == "Ister"
    choir = store.find_by_name("velmar", "The Ashen Choir")
    assert choir and choir.type == "faction"
    founding = store.find_by_name("velmar", "Founding of Velmar")
    assert founding and founding.type == "event"
    assert {f.key: f.value for f in founding.facts}["Founded"] == "312 AF"
    statuses = {e.status for e in by_id.values()} | {
        f.status for e in by_id.values() for f in e.facts
    }
    assert {"myth", "rumour", "secret"} <= statuses
    # entries name each other so mention lookups have something to find
    assert {e.title for e in store.find_mentions("velmar", ister)} >= {
        "Sky of Velmar",
        "The Ashen Choir",
    }


def test_load_seed_twice_is_idempotent(store, worlds):
    n1 = load_seed(store, worlds, SEED)
    ids1 = [e.id for e in store.list_entries("velmar")]
    n2 = load_seed(store, worlds, SEED)
    assert n1 == n2
    assert [e.id for e in store.list_entries("velmar")] == ids1
    assert len(worlds.list()) == 1


def test_first_run_creates_only_velmar_and_makes_it_active(store, worlds):
    world = ensure_first_run(store, worlds, SEED)
    assert world.id == "velmar" and world.name == "Velmar" and world.is_demo
    assert [w.id for w in worlds.list()] == ["velmar"]
    assert len(store.list_entries("velmar")) >= 15


def test_first_run_does_nothing_when_a_world_exists(store, worlds):
    mine = worlds.create("Mine")
    world = ensure_first_run(store, worlds, SEED)
    assert world.id == mine.id
    assert [w.id for w in worlds.list()] == [mine.id]
    assert store.list_entries("velmar") == []


def test_scripted_proposals_reference_existing_ids(store, worlds):
    load_seed(store, worlds, SEED)
    ids = {e.id for e in store.list_entries("velmar")}
    proposals = json.loads((SEED / "scripted_proposals.json").read_text(encoding="utf-8"))
    names = [p["name"] for p in proposals]
    assert {"three_moons", "captain_sorn"} <= set(names) and len(names) >= 3
    for p in proposals:
        EntryDraft.model_validate(p["draft"])
        assert p["action"] in {"create", "update"}
        if p["action"] == "update":
            assert p["entry_id"] in ids
        for cid in p["expect"]["conflict_ids"]:
            assert cid in ids
    three = next(p for p in proposals if p["name"] == "three_moons")
    assert three["entry_id"] == "ent_0007"
    assert "ent_0012" in three["expect"]["conflict_ids"]
    assert "Moons" in three["expect"]["retcon_keys"]
    sorn = next(p for p in proposals if p["name"] == "captain_sorn")
    assert sorn["expect"] == {"conflict_ids": [], "retcon_keys": []}


def test_seed_references_point_at_existing_ids(store, worlds):
    load_seed(store, worlds, SEED)
    entries = store.list_entries("velmar")
    ids = {e.id for e in entries}
    for e in entries:
        for link in e.links:
            assert link.target_id in ids, (e.id, link)
        for f in e.facts:
            assert set(f.refs) <= ids, (e.id, f)
            assert f.told_by is None or f.told_by in ids, (e.id, f)


def test_seed_keeps_a_rumour_fact_and_hidden_secret(store, worlds):
    load_seed(store, worlds, SEED)
    by_id = {e.id: e for e in store.list_entries("velmar")}
    vane = by_id["ent_0016"]
    assert vane.status == "canon"
    assert any(f.status == "rumour" for f in vane.facts)
    mayor = by_id["ent_0003"]
    assert any(f.status == "secret" for f in mayor.facts)
    assert "Choir" not in mayor.body


def test_failed_load_leaves_no_world_and_retry_succeeds(store, worlds):
    real = store.upsert_entry
    calls = {"n": 0}

    def flaky(entry):
        calls["n"] += 1
        if calls["n"] == 5:
            raise RuntimeError("embedding failed")
        return real(entry)

    store.upsert_entry = flaky
    with pytest.raises(RuntimeError):
        ensure_first_run(store, worlds, SEED)
    assert worlds.list() == []
    store.upsert_entry = real
    world = ensure_first_run(store, worlds, SEED)
    assert world.id == "velmar"
    assert len(store.list_entries("velmar")) == 19


def test_seed(store, worlds):
    assert load_seed(store, worlds, SEED) == 19
    ledger = store.get_entry("velmar", "ent_0019")
    assert ledger.title == "The Choir Ledger" and ledger.type == "item"
    assert ledger.status == "secret"
    assert ledger.links == []
    assert {f.key: f.value for f in ledger.facts} == {
        "Kept in": "Ilsa Corran's crypt below the Tidehall",
        "Lists": "Every member of the Ashen Choir",
        "Written in": "A cipher of moon phases",
    }
    # The Mayor's page shows a (masked) "Mentioned in" chip for the ledger.
    mayor = store.get_entry("velmar", "ent_0003")
    assert "Mayor Elsbeth Varr" in ledger.body
    assert "ent_0019" in {e.id for e in store.find_mentions("velmar", mayor, links=False)}
    assert [e.id for e in store.list_entries("velmar") if e.status == "secret"] == ["ent_0019"]


def test_seed_missing_adds_only_absent_entries(store, worlds):
    load_seed(store, worlds, SEED)
    city = store.get_entry("velmar", "ent_0001")
    store.upsert_entry(city.model_copy(update={"body": "Edited by the author."}))
    store.delete_entry("velmar", "ent_0019")
    added = seed_missing(store, SEED)
    assert [(seed_id, e.id) for seed_id, e in added] == [("ent_0019", "ent_0019")]
    assert store.get_entry("velmar", "ent_0001").body == "Edited by the author."
    assert store.get_entry("velmar", "ent_0019").title == "The Choir Ledger"
    assert len(store.list_entries("velmar")) == 19
    assert seed_missing(store, SEED) == []


def _velmar_with_sorn_at_0019(store, worlds, world_id="velmar"):
    """18-entry data, then the demo's Captain Sorn takes the next id, ent_0019."""
    load_seed(store, worlds, SEED)
    store.delete_entry("velmar", "ent_0019")
    sorn = Entry(id="ent_0019", world_id=world_id, title="Captain Sorn", type="character",
                 body="Harbourmaster of Lantern Quay.")
    return store.upsert_entry(sorn)


def test_seed_missing_re_ids_a_seed_entry_whose_id_is_taken_in_the_world(store, worlds):
    sorn = _velmar_with_sorn_at_0019(store, worlds)
    [(seed_id, ledger)] = seed_missing(store, SEED)
    assert seed_id == "ent_0019" and ledger.id == "ent_0020"
    assert store.get_entry("velmar", "ent_0020").title == "The Choir Ledger"
    assert store.get_entry("velmar", "ent_0019") == sorn  # never overwritten
    assert len(store.list_entries("velmar")) == 20
    assert seed_missing(store, SEED) == []  # the title match finds the re-id'd ledger


def test_seed_missing_re_ids_a_seed_entry_whose_id_another_world_owns(store, worlds):
    mine = _velmar_with_sorn_at_0019(store, worlds, world_id="mine")
    [(seed_id, ledger)] = seed_missing(store, SEED)
    assert seed_id == "ent_0019" and ledger.id == "ent_0020"
    assert store.get_entry("velmar", "ent_0020").title == "The Choir Ledger"
    assert store.get_entry("velmar", "ent_0019") is None
    assert store.get_entry("mine", "ent_0019") == mine
    assert seed_missing(store, SEED) == []


def test_seed_missing_does_not_re_add_a_renamed_seed_entry(store, worlds):
    load_seed(store, worlds, SEED)
    city = store.get_entry("velmar", "ent_0001")
    store.upsert_entry(city.model_copy(update={"title": "Velmar City"}))  # same id and type
    assert seed_missing(store, SEED) == []
    assert len(store.list_entries("velmar")) == 19
    assert store.get_entry("velmar", "ent_0001").title == "Velmar City"


def test_seed_missing_counts_an_entry_matching_a_seed_alias_as_present(store, worlds):
    load_seed(store, worlds, SEED)
    store.delete_entry("velmar", "ent_0002")  # The Harbour Council, alias "the Council"
    store.upsert_entry(Entry(id="ent_0030", world_id="velmar", title="The Council", type="faction",
                             body="The author's own council."))
    assert seed_missing(store, SEED) == []
    assert store.get_entry("velmar", "ent_0002") is None
