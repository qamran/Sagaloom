from pathlib import Path

from sagaloom.check.duplicate import duplicate_flags
from sagaloom.models import Entry, EntryDraft
from sagaloom.seed import load_seed
from sagaloom.store.worlds import WorldRegistry

SEED = Path(__file__).resolve().parents[3] / "seed" / "velmar"
W = "w1"


def put(store, id, title, aliases=(), status="canon"):
    store.upsert_entry(
        Entry(id=id, world_id=W, title=title, type="character", body="Someone.",
              aliases=list(aliases), status=status)
    )


def draft(title):
    return EntryDraft(title=title, type="character", body="A new face.")


def test_two_of_three_title_tokens_is_a_duplicate_note(store):
    put(store, "ent_0021", "Captain Sorn")
    [f] = duplicate_flags(store, W, draft("Captain Sorn Vey"))
    assert (f.kind, f.severity, f.entry_id, f.title) == ("note", "note", "ent_0021", "Captain Sorn")
    assert f.explanation == "Possible duplicate of ent_0021 'Captain Sorn'"
    assert f.existing_secret is False


def test_one_of_two_title_tokens_is_not(store):
    put(store, "ent_0021", "Captain Sorn")
    assert duplicate_flags(store, W, draft("Sorn")) == []


def test_alias_match_and_articles_ignored(store, tmp_path):
    load_seed(store, WorldRegistry(tmp_path / "worlds.json"), SEED)
    flags = duplicate_flags(store, "velmar", draft("Harbour Council Chamber"))
    assert [(f.entry_id, f.title) for f in flags] == [("ent_0002", "The Harbour Council")]
    put(store, "ent_0021", "Old Gate", aliases=["Sorn's Gate"])
    [f] = duplicate_flags(store, W, draft("Gate of Sorn's"))
    assert f.entry_id == "ent_0021"


def test_unrelated_title_against_the_seed_has_no_flag(store, tmp_path):
    load_seed(store, WorldRegistry(tmp_path / "worlds.json"), SEED)
    assert duplicate_flags(store, "velmar", draft("Ketra's Lantern")) == []


def test_secret_match_is_marked_secret(store):
    put(store, "ent_0021", "Captain Sorn", status="secret")
    [f] = duplicate_flags(store, W, draft("Captain Sorn Vey"))
    assert f.existing_secret is True


def test_at_most_one_flag_per_entry_and_three_in_all(store):
    put(store, "ent_0021", "Captain Sorn", aliases=["Sorn the Captain"])
    for i in range(22, 27):
        put(store, f"ent_00{i}", f"Captain Sorn {i}")
    flags = duplicate_flags(store, W, draft("Captain Sorn"))
    assert len(flags) == 3 and len({f.entry_id for f in flags}) == 3


def test_near_identical_search_hit_is_a_duplicate(store, monkeypatch):
    put(store, "ent_0021", "Moonwell")

    class Hit:
        id, score = "ent_0021", 0.95

    monkeypatch.setattr(store, "search", lambda *a, **k: [Hit()])
    [f] = duplicate_flags(store, W, draft("The Well Of Moons"))
    assert f.entry_id == "ent_0021"
    Hit.score = 0.91
    assert duplicate_flags(store, W, draft("The Well Of Moons")) == []


def test_search_failure_still_gives_token_matches(store, monkeypatch):
    put(store, "ent_0021", "Captain Sorn")

    def boom(*a, **k):
        raise RuntimeError("embeddings down")

    monkeypatch.setattr(store, "search", boom)
    assert [f.entry_id for f in duplicate_flags(store, W, draft("Captain Sorn Vey"))] == ["ent_0021"]


def test_search_hit_is_kept_ahead_of_token_matches(store, monkeypatch):
    for i in range(21, 25):
        put(store, f"ent_00{i}", f"Captain Sorn {i}")
    put(store, "ent_0030", "Moonwell")

    class Hit:
        id, score = "ent_0030", 0.95

    monkeypatch.setattr(store, "search", lambda *a, **k: [Hit()])
    flags = duplicate_flags(store, W, draft("Captain Sorn"))
    assert [f.entry_id for f in flags] == ["ent_0030", "ent_0021", "ent_0022"]
