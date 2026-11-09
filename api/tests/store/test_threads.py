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


# ---------- M3 Wave 1 Task 4 (#73): summary columns, schema once ----------

from sagaloom.store.threads import ThreadSummary  # noqa: E402

_SUMMARY_COLUMNS = {"pending", "badge", "approved", "rejected", "derived_title"}


def _columns(path) -> set[str]:
    with closing(sqlite3.connect(path)) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(threads)")}


def test_schema_checked_once_per_registry(tmp_path, monkeypatch):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    calls = []
    real = reg._migrate

    def spy(conn):
        calls.append(1)
        return real(conn)

    monkeypatch.setattr(reg, "_migrate", spy)
    tid = reg.create("w1")
    reg.get(tid)
    reg.list()
    reg.set_summary(tid, None)
    assert len(calls) == 1


def test_migrates_m1_and_m2_tables(tmp_path):
    m1, m2 = tmp_path / "m1.sqlite", tmp_path / "m2.sqlite"
    with closing(sqlite3.connect(m1)) as conn, conn:
        conn.execute(
            "CREATE TABLE threads (thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT)"
        )
        conn.execute("INSERT INTO threads VALUES ('a', 'w1', '2026-01-01T00:00:00+00:00', NULL)")
    with closing(sqlite3.connect(m2)) as conn, conn:
        conn.execute(
            "CREATE TABLE threads (thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT, kind TEXT NOT NULL DEFAULT 'chat')"
        )
        conn.execute(
            "INSERT INTO threads VALUES ('b', 'w1', '2026-01-01T00:00:00+00:00', 'n.md', 'import')"
        )
    for path, tid, kind in ((m1, "a", "chat"), (m2, "b", "import")):
        reg = ThreadRegistry(path)
        [row] = reg.list()
        assert (row.thread_id, row.kind, row.summary) == (tid, kind, None)
        assert _columns(path) >= {"kind"} | _SUMMARY_COLUMNS
        s = ThreadSummary(pending=1, badge="clear", approved=0, rejected=0, title="t")
        reg.set_summary(tid, s)
        assert ThreadRegistry(path).get(tid).summary == s


def test_set_summary_round_trip_and_clear(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    a, b = reg.create("w1"), reg.create("w1", kind="import", title="n.md")
    assert reg.get(a).summary is None  # a new row is not summarised
    s = ThreadSummary(pending=2, badge="conflict", approved=1, rejected=3, title="Add Ostra")
    reg.set_summary(a, s)
    assert reg.get(a).summary == s
    assert [t.summary for t in reg.list()] == [s, None]
    zero = ThreadSummary(pending=0, badge=None, approved=0, rejected=0, title=None)
    reg.set_summary(b, zero)
    assert reg.get(b).summary == zero  # pending 0 is a summary, not "unset"
    reg.set_summary(a, None)
    assert reg.get(a).summary is None
    assert (reg.get(a).title, reg.get(b).title, reg.get(b).kind) == (None, "n.md", "import")
    reg.set_summary("nope", s)  # an unknown id is a no-op
    assert reg.get("nope") is None


def test_set_summary_if_unset_never_overwrites(tmp_path):
    reg = ThreadRegistry(tmp_path / "t.sqlite")
    tid = reg.create("w1")
    first = ThreadSummary(pending=1, badge="clear", approved=0, rejected=0, title="a")
    second = ThreadSummary(pending=0, badge=None, approved=1, rejected=0, title="a")
    reg.set_summary_if_unset(tid, first)
    assert reg.get(tid).summary == first
    reg.set_summary_if_unset(tid, second)
    assert reg.get(tid).summary == first
    reg.set_summary(tid, None)
    reg.set_summary_if_unset(tid, second)
    assert reg.get(tid).summary == second
    reg.set_summary_if_unset("nope", first)
    assert reg.get("nope") is None
