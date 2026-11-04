import json
from pathlib import Path

import pytest

from sagaloom.models import Entry, EntryDraft
from sagaloom.seed import ensure_first_run, load_seed
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
