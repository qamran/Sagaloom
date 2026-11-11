import json
import re
import threading

import pytest

from sagaloom.store import worlds as worlds_module
from sagaloom.store.worlds import WorldRegistry


def test_world_registry_persists_to_disk(tmp_path):
    path = tmp_path / "data" / "worlds.json"
    reg = WorldRegistry(path)
    assert reg.all_worlds() == []
    w = reg.create("Velmar", world_id="velmar", is_demo=True)
    reg2 = WorldRegistry(path)
    assert reg2.get("velmar") == w
    assert reg2.all_worlds() == [w]
    assert reg2.get("nope") is None


def test_list_filters_by_owner(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    a = reg.create("A", owner_id="u1")
    b = reg.create("B", owner_id="u2")
    c = reg.create("C", owner_id=None)
    assert reg.all_worlds() == [a, b, c]
    assert reg.list(owner_id="u1") == [a]
    assert reg.owned_by("u2") == [b]


def test_listing_fails_closed_without_an_owner(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    reg.create("A", owner_id=None)
    reg.create("B", owner_id="u1")
    assert reg.owned_by(None) == []
    assert reg.list(None) == []
    with pytest.raises(TypeError):
        reg.list()  # the owner is required


def test_assign_unowned_only_takes_ownerless(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    reg.create("A", owner_id="u1")
    reg.create("B", owner_id=None)
    reg.create("C", owner_id=None)
    assert reg.assign_unowned("u2") == ["b", "c"]
    assert [w.owner_id for w in reg.all_worlds()] == ["u1", "u2", "u2"]
    assert reg.assign_unowned("u3") == []


def test_legacy_worlds_json_loads_with_owner_none(tmp_path):
    path = tmp_path / "worlds.json"
    path.write_text(
        '[{"id": "velmar", "name": "Velmar", "is_demo": true, "divergent": false}]', encoding="utf-8"
    )
    [world] = WorldRegistry(path).all_worlds()
    assert world.owner_id is None


def test_concurrent_writes_lose_nothing(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    for i in range(10):
        reg.create(f"Old {i}", owner_id=None)
    start = threading.Barrier(21)

    def make(i):
        start.wait()
        reg.create(f"New {i}", owner_id="u1")

    def assign():
        start.wait()
        reg.assign_unowned("admin")

    threads = [threading.Thread(target=make, args=(i,)) for i in range(20)]
    threads.append(threading.Thread(target=assign))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    worlds = WorldRegistry(tmp_path / "worlds.json").all_worlds()
    assert len(worlds) == 30 and len({w.id for w in worlds}) == 30
    assert [w.owner_id for w in worlds if w.name.startswith("Old")] == ["admin"] * 10
    assert all(w.owner_id == "u1" for w in worlds if w.name.startswith("New"))


def test_failed_write_leaves_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "worlds.json"
    reg = WorldRegistry(path)
    reg.create("A", owner_id="u1")
    before = path.read_text(encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(worlds_module.os, "replace", boom)
    with pytest.raises(OSError):
        reg.create("B", owner_id="u1")
    assert path.read_text(encoding="utf-8") == before
    assert [p.name for p in tmp_path.iterdir()] == ["worlds.json"]  # no temp file left
    assert [w["id"] for w in json.loads(before)] == ["a"]


SUFFIXED = r"velmar-[a-z0-9]{4}"


def test_reserved_id_is_skipped_until_created_or_released(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    reg.create("Velmar", world_id="velmar")
    rid = reg.reserve_id("Velmar")
    assert re.fullmatch(SUFFIXED, rid)
    other = reg.create("Velmar").id  # another create does not take it
    assert re.fullmatch(SUFFIXED, other) and other != rid
    assert reg.create("Velmar", owner_id="u1", world_id=rid).id == rid
    gone = reg.reserve_id("Gone")
    reg.release(gone)
    assert reg.create("Gone").id == gone


def test_collision_gets_a_random_suffix_not_a_counter(tmp_path):
    """Spec §5.4: ids reveal nothing about other accounts' worlds or how many there are."""
    reg = WorldRegistry(tmp_path / "worlds.json")
    assert reg.create("Secret Project", owner_id="u1").id == "secret-project"
    second = reg.create("Secret Project", owner_id="u2").id
    assert re.fullmatch(r"secret-project-[a-z0-9]{4}", second), second
    ids = {reg.create("Secret Project", owner_id="u3").id for _ in range(5)}
    assert len(ids) == 5 and "secret-project-2" not in ids


def test_suffix_retries_on_collision(tmp_path, monkeypatch):
    reg = WorldRegistry(tmp_path / "worlds.json")
    reg.create("Velmar")
    reg.create("Velmar", world_id="velmar-aaaa")
    picks = iter("aaaa" + "bbbb")
    monkeypatch.setattr(worlds_module.secrets, "choice", lambda alphabet: next(picks))
    assert reg.create("Velmar").id == "velmar-bbbb"


def test_candidate_with_existing_records_is_skipped(tmp_path):
    """A lost worlds.json must not hand a new account the old world's records."""
    reg = WorldRegistry(tmp_path / "worlds.json")
    has_records = {"velmar", "atlas"}.__contains__
    assert reg.create("Atlas", in_use=has_records).id != "atlas"
    rid = reg.reserve_id("Velmar", in_use=has_records)
    assert re.fullmatch(SUFFIXED, rid)
    assert reg.create("Fresh", in_use=has_records).id == "fresh"
