import uuid

import chromadb
import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from pydantic import ValidationError

from sagaloom.models import Entry, EntrySource, Fact, Link
from sagaloom.store.canon import CanonStore, DuplicateTitleError, VersionConflictError, norm


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
    assert store.next_entry_id("w1") == "ent_0001"
    store.upsert_entry(mk(id="ent_0020"))
    store.upsert_entry(mk(id="ent_0003", title="Other"))
    assert store.next_entry_id("w1") == "ent_0021"


# ---------- per-world entry ids (M5) ----------


def test_same_entry_id_in_two_worlds(store):
    store.upsert_entry(mk(id="ent_0001", world="a", title="X"))
    store.upsert_entry(mk(id="ent_0001", world="b", title="Y"))
    assert store.get_entry("a", "ent_0001").title == "X"
    assert store.get_entry("b", "ent_0001").title == "Y"
    assert [e.id for e in store.list_entries("a")] == ["ent_0001"]
    assert [h.id for h in store.search("b", "Y")] == ["ent_0001"]


def test_next_entry_id_is_per_world(store):
    store.upsert_entry(mk(id="ent_0005", world="a"))
    assert store.next_entry_id("b") == "ent_0001"
    assert store.next_entry_id("a") == "ent_0006"


def test_has_id_is_per_world(store):
    store.upsert_entry(mk(id="ent_0002", world="a"))
    assert store.has_id("a", "ent_0002")
    assert not store.has_id("b", "ent_0002")


def test_delete_only_touches_its_world(store):
    store.upsert_entry(mk(id="ent_0001", world="a", title="X"))
    store.upsert_entry(mk(id="ent_0001", world="b", title="Y"))
    store.delete_entry("a", "ent_0001")
    assert store.get_entry("a", "ent_0001") is None
    assert store.get_entry("b", "ent_0001").title == "Y"


class CountingEmbeddings(DeterministicFakeEmbedding):
    """Counts the texts embedded, so a test can tell a copy from a re-embed."""

    calls: int = 0

    def embed_documents(self, texts):
        self.calls += len(texts)
        return super().embed_documents(texts)

    def embed_query(self, text):
        self.calls += 1
        return super().embed_query(text)


def test_migrate_record_ids_rekeys_legacy_records():
    emb = CountingEmbeddings(size=16)
    store = CanonStore(chromadb.EphemeralClient(), emb, collection_name=f"e_{uuid.uuid4().hex}")
    legacy = mk(id="ent_0003", world="velmar", title="Lantern Quay")
    vector = [0.25] * 16
    doc = "Lantern Quay\n\nA moon."
    store.col.upsert(
        ids=["ent_0003"],
        documents=[doc],
        embeddings=[vector],
        metadatas=[
            {
                "world_id": "velmar",
                "type": "place",
                "status": "canon",
                "title_norm": norm(legacy.title),
                "entry_json": legacy.model_dump_json(),
            }
        ],
    )
    store.upsert_entry(mk(id="ent_0001", world="velmar", title="Already keyed"))
    before = emb.calls
    assert store.migrate_record_ids() == 1
    assert store.get_entry("velmar", "ent_0003") == legacy
    assert store.has_id("velmar", "ent_0003")
    assert store.migrate_record_ids() == 0
    assert emb.calls == before  # copied, never re-embedded
    got = store.col.get(ids=["velmar/ent_0003"], include=["embeddings", "documents"])
    assert [float(x) for x in got["embeddings"][0]] == pytest.approx(vector)
    assert got["documents"] == [doc]
    assert store.col.get(ids=["ent_0003"], include=[])["ids"] == []
    assert sorted(store.col.get(include=[])["ids"]) == ["velmar/ent_0001", "velmar/ent_0003"]


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


def test_name_index_matches_find_by_name(store):
    """One canon read gives every title and alias; the first entry by id wins a shared name."""
    store.upsert_entry(mk(id="ent_0001", title="Ister", aliases=["Pale Moon"]))
    store.upsert_entry(mk(id="ent_0002", title="Second Moon", aliases=["Ister"]))
    index = store.name_index("w1")
    assert index["ister"].id == "ent_0001"
    assert index["pale moon"].id == "ent_0001"
    assert index["second moon"].id == "ent_0002"
    for name in ["ISTER", "pale  moon", "nope"]:
        assert store.find_by_name("w1", name) == index.get(norm(name))
    assert store.find_by_name("w1", "ISTER").id == "ent_0001"
    assert store.find_by_name("w1", "nope") is None


def test_find_dependents_finds_links_and_title_mentions(store):
    target = store.upsert_entry(mk(id="ent_0001", title="Ister", aliases=["The Pale"]))
    store.upsert_entry(mk(id="ent_0002", title="Linker", body="nothing here", links=[Link(target_id="ent_0001", relation="sees")]))
    store.upsert_entry(mk(id="ent_0003", title="Titler", body="Under ISTER's light"))
    store.upsert_entry(mk(id="ent_0004", title="Aliaser", body="the pale glows"))
    store.upsert_entry(mk(id="ent_0005", title="Unrelated", body="Dry land"))
    store.upsert_entry(mk(id="ent_0006", world="w2", title="Other", body="Ister"))
    got = {e.id for e, _ in store.find_dependents("w1", target)}
    assert got == {"ent_0002", "ent_0003", "ent_0004"}
    assert {e.id for e in store.mentioned_in("w1", "We saw ister rise")} == {"ent_0001"}


def test_find_mentions_is_text_only(store):
    target = store.upsert_entry(mk(id="ent_0001", title="Ister", aliases=["The Pale"]))
    store.upsert_entry(mk(id="ent_0002", title="Linker", body="nothing here", links=[Link(target_id="ent_0001", relation="sees")]))
    store.upsert_entry(mk(id="ent_0003", title="Titler", body="Under ISTER's light"))
    store.upsert_entry(mk(id="ent_0004", title="Aliaser", body="the pale glows"))
    got = {e.id for e in store.find_mentions("w1", target)}
    assert got == {"ent_0003", "ent_0004"}


def test_search_hit_of_secret_entry_has_empty_snippet(store):
    store.upsert_entry(
        mk(id="ent_0001", title="The Vault", body="Hidden gold below the keep.", status="secret",
           facts=[Fact(key="Holds", value="Gold")])
    )
    store.upsert_entry(mk(id="ent_0002", title="The Keep", body="A tower above the vault."))
    hits = {h.id: h for h in store.search("w1", "vault")}
    vault = hits["ent_0001"]
    assert vault.title == "The Vault" and vault.status == "secret"
    assert vault.snippet == "" and vault.facts == []
    assert hits["ent_0002"].snippet == "A tower above the vault."


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


def test_search_hits_carry_non_secret_facts_only(store):
    store.upsert_entry(
        mk(
            facts=[
                Fact(key="Colour", value="Red"),
                Fact(key="Moons", value="Three", status="myth"),
                Fact(key="Whispered", value="Heard at the dock", status="rumour"),
                Fact(key="Hidden", value="Buried under the quay", status="secret"),
            ]
        )
    )
    (hit,) = store.search("w1", "Ister")
    assert [(f.key, f.value, f.status) for f in hit.facts] == [
        ("Colour", "Red", "canon"),
        ("Moons", "Three", "myth"),
        ("Whispered", "Heard at the dock", "rumour"),
    ]
    assert "Buried" not in hit.model_dump_json()


def test_secret_entry_hit_has_no_facts(store):
    store.upsert_entry(mk(status="secret", facts=[Fact(key="Where", value="Under the quay")]))
    (hit,) = store.search("w1", "Ister")
    assert hit.facts == []


# ---------- version guard (#63) ----------


def test_upsert_refuses_stale_version(store):
    v1 = store.upsert_entry(mk())
    v2 = store.upsert_entry(v1.model_copy(update={"body": "Second.", "version": 2}))
    with pytest.raises(VersionConflictError) as exc:
        store.upsert_entry(v1.model_copy(update={"body": "Stale.", "version": 2}), expected_version=1)
    assert isinstance(exc.value, ValueError)
    assert (exc.value.entry_id, exc.value.expected, exc.value.actual) == ("ent_0001", 1, 2)
    assert store.get_entry("w1", "ent_0001") == v2


def test_upsert_create_refuses_existing_id(store):
    v1 = store.upsert_entry(mk())
    with pytest.raises(VersionConflictError) as exc:
        store.upsert_entry(mk(body="Another."), expected_version=0)
    assert (exc.value.expected, exc.value.actual) == (0, 1)
    assert store.get_entry("w1", "ent_0001") == v1


def test_upsert_with_matching_expected_version_writes(store):
    store.upsert_entry(mk(), expected_version=0)
    v1 = store.get_entry("w1", "ent_0001")
    saved = store.upsert_entry(v1.model_copy(update={"body": "B", "version": 2}), expected_version=1)
    assert store.get_entry("w1", "ent_0001") == saved and saved.version == 2


def test_upsert_without_expected_version_unchanged(store):
    store.upsert_entry(mk(version=3))
    saved = store.upsert_entry(mk(body="Overwritten.", version=1))
    assert store.get_entry("w1", "ent_0001") == saved and saved.body == "Overwritten."


def test_sources_round_trip_through_chroma(store):
    sources = [
        EntrySource(
            kind="official", url="https://lotr.fandom.com/wiki/Gandalf", licence="CC BY-NC-SA 3.0",
            licence_url="https://creativecommons.org/licenses/by-nc-sa/3.0/", nc=True,
        ),
        EntrySource(kind="reference", url="https://en.wikipedia.org/wiki/Wizard"),
    ]
    saved = store.upsert_entry(mk(source="official", trusted=False, sources=sources))
    got = store.get_entry("w1", "ent_0001")
    assert got == saved and got.sources == sources
    assert store.list_entries("w1")[0].sources == sources


def _legacy(store, entry, doc="legacy doc"):
    """A record as stored before ids were per world: record id == entry id."""
    store.col.upsert(
        ids=[entry.id],
        documents=[doc],
        embeddings=[[0.5] * 256],
        metadatas=[
            {
                "world_id": entry.world_id,
                "type": entry.type,
                "status": entry.status,
                "title_norm": norm(entry.title),
                "entry_json": entry.model_dump_json(),
            }
        ],
    )


def test_migrate_record_ids_skips_a_target_that_exists(store):
    kept = store.upsert_entry(mk(id="ent_0001", world="velmar", title="Already keyed"))
    _legacy(store, mk(id="ent_0001", world="velmar", title="Stale legacy copy"))
    assert store.migrate_record_ids() == 0
    assert store.get_entry("velmar", "ent_0001") == kept
    assert store.col.get(include=[])["ids"] == ["velmar/ent_0001"]  # the legacy record is gone


def test_migrate_record_ids_works_in_chunks(store, monkeypatch):
    for i in range(1, 6):
        _legacy(store, mk(id=f"ent_{i:04d}", world="velmar", title=f"T{i}"))
    monkeypatch.setattr(store, "_batch_size", 2)
    sizes = []
    real_get = store.col.get

    def get(*args, **kwargs):
        if kwargs.get("ids") is not None:
            sizes.append(len(kwargs["ids"]))
        return real_get(*args, **kwargs)

    monkeypatch.setattr(store.col, "get", get)
    assert store.migrate_record_ids() == 5
    assert sizes and max(sizes) <= 2
    assert sorted(real_get(include=[])["ids"]) == [f"velmar/ent_{i:04d}" for i in range(1, 6)]


class BatchCountingEmbeddings(DeterministicFakeEmbedding):
    """Counts `embed_documents` calls (not texts)."""

    batches: int = 0

    def embed_documents(self, texts):
        self.batches += 1
        return super().embed_documents(texts)


def test_upsert_entries_embeds_in_one_call():
    emb = BatchCountingEmbeddings(size=16)
    store = CanonStore(chromadb.EphemeralClient(), emb, collection_name=f"e_{uuid.uuid4().hex}")
    entries = [mk(id=f"ent_{i:04d}", title=f"Place {i}") for i in range(1, 6)]
    stored = store.upsert_entries(entries)
    assert emb.batches == 1
    assert [e.id for e in store.list_entries("w1")] == [e.id for e in entries]
    assert [e.title for e in stored] == [e.title for e in entries]
    assert all(e.updated_at for e in stored)
    assert store.get_entry("w1", "ent_0003") == stored[2]
    assert store.find_by_name("w1", "place 4").id == "ent_0004"


def test_upsert_entries_keeps_the_single_write_checks(store):
    store.upsert_entry(mk(id="ent_0001", title="Ister"))
    with pytest.raises(DuplicateTitleError):  # against the stored entries
        store.upsert_entries([mk(id="ent_0002", title="Ostra"), mk(id="ent_0003", title=" ISTER ")])
    with pytest.raises(DuplicateTitleError):  # within the batch
        store.upsert_entries([mk(id="ent_0002", title="Ostra"), mk(id="ent_0003", title="ostra")])
    with pytest.raises(VersionConflictError):  # new entries only: an existing id is refused
        store.upsert_entries([mk(id="ent_0002", title="Ostra"), mk(id="ent_0001", title="Other")])
    assert [e.id for e in store.list_entries("w1")] == ["ent_0001"]  # nothing written
    assert store.upsert_entries([]) == []


def test_has_world(store):
    assert not store.has_world("w1")
    store.upsert_entry(mk())
    assert store.has_world("w1") and not store.has_world("w2")
