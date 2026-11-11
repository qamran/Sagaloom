from sagaloom.store.worlds import WorldRegistry


def test_world_registry_persists_to_disk(tmp_path):
    path = tmp_path / "data" / "worlds.json"
    reg = WorldRegistry(path)
    assert reg.list() == []
    w = reg.create("Velmar", world_id="velmar", is_demo=True)
    reg2 = WorldRegistry(path)
    assert reg2.get("velmar") == w
    assert reg2.list() == [w]
    assert reg2.get("nope") is None


def test_list_filters_by_owner(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    a = reg.create("A", owner_id="u1")
    b = reg.create("B", owner_id="u2")
    c = reg.create("C", owner_id=None)
    assert reg.list() == [a, b, c]
    assert reg.list(owner_id="u1") == [a]
    assert reg.owned_by("u2") == [b]


def test_assign_unowned_only_takes_ownerless(tmp_path):
    reg = WorldRegistry(tmp_path / "worlds.json")
    reg.create("A", owner_id="u1")
    reg.create("B", owner_id=None)
    reg.create("C", owner_id=None)
    assert reg.assign_unowned("u2") == ["b", "c"]
    assert [w.owner_id for w in reg.list()] == ["u1", "u2", "u2"]
    assert reg.assign_unowned("u3") == []


def test_legacy_worlds_json_loads_with_owner_none(tmp_path):
    path = tmp_path / "worlds.json"
    path.write_text(
        '[{"id": "velmar", "name": "Velmar", "is_demo": true, "divergent": false}]', encoding="utf-8"
    )
    [world] = WorldRegistry(path).list()
    assert world.owner_id is None
