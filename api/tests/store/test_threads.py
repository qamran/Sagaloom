from sagaloom.store.threads import ThreadRegistry


def test_create_get_list(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    a, b = reg.create("w1"), reg.create("w2")
    assert len(a) == 32 and a != b
    assert reg.get(a).world_id == "w1" and reg.get("nope") is None
    assert [t.thread_id for t in reg.list()] == [a, b]
    assert [t.thread_id for t in ThreadRegistry(tmp_path / "t.sqlite").list("w2")] == [b]
