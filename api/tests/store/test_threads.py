import sqlite3
from contextlib import closing

from sagaloom.store.threads import ThreadRegistry


def test_create_get_list(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    a, b = reg.create("w1"), reg.create("w2")
    assert len(a) == 32 and a != b
    assert reg.get(a).world_id == "w1" and reg.get("nope") is None
    assert [t.thread_id for t in reg.list()] == [a, b]
    assert [t.thread_id for t in ThreadRegistry(tmp_path / "t.sqlite").list("w2")] == [b]


def test_create_defaults_to_chat_and_stores_kind_and_title(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    chat = reg.create("w1")
    imp = reg.create("w1", kind="import", title="session-12-notes.md")
    assert (reg.get(chat).kind, reg.get(chat).title) == ("chat", None)
    assert (reg.get(imp).kind, reg.get(imp).title) == ("import", "session-12-notes.md")


def test_list_filters_by_kind(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    chat, imp = reg.create("w1"), reg.create("w1", kind="import")
    other = reg.create("w2", kind="import")
    assert [t.thread_id for t in reg.list(kind="import")] == [imp, other]
    assert [t.thread_id for t in reg.list("w1", kind="chat")] == [chat]
    assert [t.thread_id for t in reg.list("w1", kind="import")] == [imp]
    assert [t.thread_id for t in reg.list("w1")] == [chat, imp]


def test_delete_removes_row(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    a, b = reg.create("w1"), reg.create("w1")
    assert reg.delete(a) is None
    assert reg.get(a) is None and [t.thread_id for t in reg.list()] == [b]
    reg.delete("nope")  # unknown id is a no-op


def test_old_table_without_kind_is_migrated(tmp_path):
    path = tmp_path / "t.sqlite"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE threads (thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT)"
        )
        conn.execute(
            "INSERT INTO threads VALUES (?, ?, ?, ?)", ("old", "w1", "2026-01-01T00:00:00+00:00", "M1")
        )
    reg = ThreadRegistry(path)
    [row] = reg.list()
    assert (row.thread_id, row.kind, row.title) == ("old", "chat", "M1")
    new = reg.create("w1", kind="import")
    assert [t.thread_id for t in ThreadRegistry(path).list(kind="import")] == [new]
