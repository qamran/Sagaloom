import pytest
from pydantic import ValidationError

from sagaloom.models import Entry, Fact, Link
from sagaloom.store.canon import DuplicateTitleError


def mk(id="ent_0001", world="w1", title="Ister", type="place", body="A moon.", **kw):
    return Entry(id=id, world_id=world, title=title, type=type, body=body, **kw)


def test_upsert_and_get_roundtrip_keeps_all_fields(store):
    e = mk(
        status="myth",
        source="official",
        source_url="https://w.example/x",
        licence="CC BY-SA 3.0",
        trusted=False,
        aliases=["The Pale"],
        links=[Link(target_id="ent_0002", relation="orbits")],
        facts=[Fact(key="Moons", value="One", refs=["ent_0002"], status="rumour", told_by="ent_0003")],
    )
    saved = store.upsert_entry(e)
    assert store.get_entry("w1", "ent_0001") == saved
    assert saved.model_dump(exclude={"updated_at"}) == e.model_dump(exclude={"updated_at"})
    assert store.get_entry("w2", "ent_0001") is None


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        Entry(id="ent_0001", world_id="w1", title="x", type="spell", body="")


def test_id_stable_across_update_and_version_increments(store):
    store.upsert_entry(mk())
    e = store.get_entry("w1", "ent_0001")
    store.upsert_entry(e.model_copy(update={"body": "Changed", "version": e.version + 1}))
    got = store.get_entry("w1", "ent_0001")
    assert got.id == "ent_0001" and got.version == 2 and got.body == "Changed"
    assert len(store.list_entries("w1")) == 1


def test_next_entry_id_continues_after_highest(store):
    assert store.next_entry_id() == "ent_0001"
    store.upsert_entry(mk(id="ent_0020", world="w2"))
    store.upsert_entry(mk(id="ent_0003", title="Other"))
    assert store.next_entry_id() == "ent_0021"


def test_search_scoped_to_world(store):
    store.upsert_entry(mk(id="ent_0001", world="w1"))
    store.upsert_entry(mk(id="ent_0002", world="w2"))
    hits = store.search("w1", "Ister")
    assert [h.id for h in hits] == ["ent_0001"]


def test_search_empty_world_returns_empty_list(store):
    assert store.search("nothing", "Ister") == []


def test_search_clamps_k_to_10(store):
    for i in range(1, 13):
        store.upsert_entry(mk(id=f"ent_{i:04d}", title=f"T{i}", body=f"body {i}"))
    assert len(store.search("w1", "body", k=50)) == 10
    assert len(store.search("w1", "body")) == 5
    scores = [h.score for h in store.search("w1", "body", k=10)]
    assert scores == sorted(scores, reverse=True)


def test_search_filters_types_and_statuses(store):
    store.upsert_entry(mk(id="ent_0001", title="A", type="place"))
    store.upsert_entry(mk(id="ent_0002", title="B", type="character", status="myth"))
    assert [h.id for h in store.search("w1", "x", entry_types=["character"])] == ["ent_0002"]
    assert [h.id for h in store.search("w1", "x", statuses=["canon"])] == ["ent_0001"]
    assert store.search("w1", "x", entry_types=["place"], statuses=["myth"]) == []


def test_find_by_name_ignores_case_and_curly_quotes(store):
    store.upsert_entry(mk(title="The old king's drowning", type="event", aliases=["Grey Tide"]))
    assert store.find_by_name("w1", "the Old King’s Drowning").id == "ent_0001"
    assert store.find_by_name("w1", "  grey   TIDE").id == "ent_0001"
    assert store.find_by_name("w1", "nope") is None


def test_find_mentions_finds_links_and_title_mentions(store):
    target = store.upsert_entry(mk(id="ent_0001", title="Ister", aliases=["The Pale"]))
    store.upsert_entry(mk(id="ent_0002", title="Linker", body="nothing here", links=[Link(target_id="ent_0001", relation="sees")]))
    store.upsert_entry(mk(id="ent_0003", title="Titler", body="Under ISTER's light"))
    store.upsert_entry(mk(id="ent_0004", title="Aliaser", body="the pale glows"))
    store.upsert_entry(mk(id="ent_0005", title="Unrelated", body="Dry land"))
    store.upsert_entry(mk(id="ent_0006", world="w2", title="Other", body="Ister"))
    got = {e.id for e in store.find_mentions("w1", target)}
    assert got == {"ent_0002", "ent_0003", "ent_0004"}
    assert {e.id for e in store.mentioned_in("w1", "We saw ister rise")} == {"ent_0001"}


def test_duplicate_title_in_same_world_rejected_case_insensitively(store):
    store.upsert_entry(mk(id="ent_0001", title="Ister"))
    with pytest.raises(DuplicateTitleError):
        store.upsert_entry(mk(id="ent_0002", title="  ISTER "))
    store.upsert_entry(mk(id="ent_0002", world="w2", title="ister"))
    store.upsert_entry(mk(id="ent_0001", title="Ister", body="same entry ok"))


def test_delete_entry(store):
    store.upsert_entry(mk())
    store.delete_entry("w1", "ent_0001")
    assert store.get_entry("w1", "ent_0001") is None
