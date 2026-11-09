import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ThreadKind = Literal["chat", "import"]

_COLUMNS = ("thread_id", "world_id", "created_at", "title", "kind")
# The list summary (M3 #73). `pending IS NULL` means "not summarised".
_SUMMARY_COLUMNS = ("pending", "badge", "approved", "rejected", "derived_title")
_SUMMARY_TYPES = {
    "pending": "INTEGER",
    "badge": "TEXT",
    "approved": "INTEGER",
    "rejected": "INTEGER",
    "derived_title": "TEXT",
}
_SELECT = f"SELECT {', '.join(_COLUMNS + _SUMMARY_COLUMNS)} FROM threads"


class ThreadSummary(BaseModel):
    """What `GET /threads` shows for a thread, read once from its checkpoint. `badge` is a plain
    `str` so the store does not depend on `check`; `title` is the derived title."""

    pending: int
    badge: str | None = None
    approved: int
    rejected: int
    title: str | None = None


class ThreadInfo(BaseModel):
    thread_id: str
    world_id: str
    created_at: str
    title: str | None = None
    kind: ThreadKind = "chat"
    summary: ThreadSummary | None = None


def _info(row: tuple) -> ThreadInfo:
    base = dict(zip(_COLUMNS, row[: len(_COLUMNS)]))
    pending, badge, approved, rejected, derived = row[len(_COLUMNS) :]
    summary = (
        None
        if pending is None
        else ThreadSummary(
            pending=pending, badge=badge, approved=approved or 0, rejected=rejected or 0, title=derived
        )
    )
    return ThreadInfo(**base, summary=summary)


def _summary_values(summary: ThreadSummary | None) -> tuple:
    if summary is None:
        return (None,) * len(_SUMMARY_COLUMNS)
    return (summary.pending, summary.badge, summary.approved, summary.rejected, summary.title)


_SET_SUMMARY = "UPDATE threads SET " + ", ".join(f"{c} = ?" for c in _SUMMARY_COLUMNS)


class ThreadRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._ready = False
        self._ready_lock = threading.Lock()  # sync routes run in a thread pool

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Creates the table, or brings an older one up to date: an M1 table has no `kind` (every
        thread then was a chat), and an M1 or M2 table has no summary columns."""
        conn.execute(
            "CREATE TABLE IF NOT EXISTS threads ("
            "thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT, kind TEXT NOT NULL DEFAULT 'chat', "
            + ", ".join(f"{c} {_SUMMARY_TYPES[c]}" for c in _SUMMARY_COLUMNS)
            + ")"
        )
        have = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
        if "kind" not in have:
            conn.execute("ALTER TABLE threads ADD COLUMN kind TEXT NOT NULL DEFAULT 'chat'")
        for column in _SUMMARY_COLUMNS:
            if column not in have:
                conn.execute(f"ALTER TABLE threads ADD COLUMN {column} {_SUMMARY_TYPES[column]}")
        conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """A connection to a table that is known to be up to date. The schema is checked once
        per registry instance, not on every connect."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        if not self._ready:
            with self._ready_lock:
                if not self._ready:
                    try:
                        self._migrate(conn)
                    except BaseException:
                        conn.close()
                        raise
                    self._ready = True
        return conn

    def create(self, world_id: str, kind: ThreadKind = "chat", title: str | None = None) -> str:
        thread_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO threads (thread_id, world_id, created_at, title, kind) "
                "VALUES (?, ?, ?, ?, ?)",
                (thread_id, world_id, datetime.now(UTC).isoformat(), title, kind),
            )
        return thread_id

    def get(self, thread_id: str) -> ThreadInfo | None:
        with closing(self._connect()) as conn:
            row = conn.execute(_SELECT + " WHERE thread_id = ?", (thread_id,)).fetchone()
        return _info(row) if row else None

    def list(self, world_id: str | None = None, kind: ThreadKind | None = None) -> list[ThreadInfo]:
        where: list[str] = []
        args: list[str] = []
        if world_id is not None:
            where.append("world_id = ?")
            args.append(world_id)
        if kind is not None:
            where.append("kind = ?")
            args.append(kind)
        sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        return [_info(r) for r in rows]

    def set_summary(self, thread_id: str, summary: ThreadSummary | None) -> None:
        """Stores the list summary; None clears it. An unknown id is a no-op."""
        with closing(self._connect()) as conn, conn:
            conn.execute(_SET_SUMMARY + " WHERE thread_id = ?", (*_summary_values(summary), thread_id))

    def set_summary_if_unset(self, thread_id: str, summary: ThreadSummary) -> None:
        """Stores the summary only where none is stored, so a lazy fill never overwrites the one a
        turn wrote. An unknown id is a no-op."""
        with closing(self._connect()) as conn, conn:
            conn.execute(
                _SET_SUMMARY + " WHERE thread_id = ? AND pending IS NULL",
                (*_summary_values(summary), thread_id),
            )

    def delete(self, thread_id: str) -> None:
        """Removes the registry row only (the checkpoint stays). Unknown ids are a no-op."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
