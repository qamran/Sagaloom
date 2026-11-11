"""`scripts/reassign_owner.py`: moves a user's worlds and costs to a new Clerk user id."""

import importlib.util
from pathlib import Path

import pytest

from sagaloom.promptlog import PromptLog, PromptRecord
from sagaloom.store.worlds import WorldRegistry

API = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("reassign_owner", API / "scripts" / "reassign_owner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(id: str, thread_id: str) -> PromptRecord:
    return PromptRecord(
        id=id,
        thread_id=thread_id,
        run_id="r",
        started_at="2026-11-11T10:00:00+00:00",
        provider="openai",
        model="m",
        request={"messages": [], "tools": []},
    )


def _owners(log: PromptLog) -> dict[str, str | None]:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(log.path)) as conn:
        return dict(conn.execute("SELECT id, user_id FROM prompt_log").fetchall())


@pytest.fixture
def data(tmp_path):
    worlds = WorldRegistry(tmp_path / "worlds.json")
    worlds.create("Velmar", owner_id="user_old", is_demo=True)
    worlds.create("Harbour Notes", owner_id="user_old")
    worlds.create("Velmar", owner_id="user_other", is_demo=True)
    worlds.create("Legacy", owner_id=None)
    log = PromptLog(tmp_path / "prompts.sqlite")
    log.add(_record("a", "t1"), user_id="user_old")
    log.add(_record("b", "t2"), user_id="user_old")
    log.add(_record("c", "t3"), user_id="user_other")
    log.add(_record("d", "t4"), user_id=None)
    return tmp_path


def test_moves_only_the_old_users_worlds_and_costs(data):
    moved_worlds, moved_records = _script().reassign(data, "user_old", "user_new")
    assert sorted(moved_worlds) == ["harbour-notes", "velmar"]
    assert moved_records == 2
    owners = {w.id: w.owner_id for w in WorldRegistry(data / "worlds.json").all_worlds()}
    assert owners["velmar"] == owners["harbour-notes"] == "user_new"
    assert [w for w, o in owners.items() if o == "user_other"] != []
    assert [w for w, o in owners.items() if o is None] == ["legacy"]
    assert _owners(PromptLog(data / "prompts.sqlite")) == {
        "a": "user_new",
        "b": "user_new",
        "c": "user_other",
        "d": None,
    }


def test_same_id_is_refused(data):
    with pytest.raises(ValueError):
        _script().reassign(data, "user_old", "user_old")


def test_empty_id_is_refused(data):
    with pytest.raises(ValueError):
        _script().reassign(data, "user_old", " ")


def test_unknown_old_id_changes_nothing(data):
    assert _script().reassign(data, "user_nobody", "user_new") == ([], 0)
    assert "user_new" not in {w.owner_id for w in WorldRegistry(data / "worlds.json").all_worlds()}


def test_main_prints_the_counts(data, capsys):
    assert _script().main(["user_old", "user_new", "--data-dir", str(data)]) == 0
    out = capsys.readouterr().out
    assert "2 world(s)" in out and "2 prompt record(s)" in out


def test_main_refuses_the_same_id(data, capsys):
    assert _script().main(["user_old", "user_old", "--data-dir", str(data)]) == 2
    assert "different" in capsys.readouterr().err


def test_missing_worlds_file_is_refused_and_creates_nothing(tmp_path, capsys):
    wrong = tmp_path / "not-the-data-dir"
    wrong.mkdir()
    assert _script().main(["user_old", "user_new", "--data-dir", str(wrong)]) == 2
    assert "worlds.json" in capsys.readouterr().err
    assert list(wrong.iterdir()) == []


def test_old_id_with_nothing_to_move_warns_and_fails(data, capsys):
    assert _script().main(["user_nobody", "user_new", "--data-dir", str(data)]) == 1
    assert "owns no world" in capsys.readouterr().err


def test_dry_run_reports_and_changes_nothing(data, capsys):
    before = (data / "worlds.json").read_text(encoding="utf-8")
    assert _script().main(["user_old", "user_new", "--data-dir", str(data), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would move 2 world(s) and 2 prompt record(s)" in out
    assert "velmar" in out and "harbour-notes" in out
    assert (data / "worlds.json").read_text(encoding="utf-8") == before
    assert _owners(PromptLog(data / "prompts.sqlite"))["a"] == "user_old"
