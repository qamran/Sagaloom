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
