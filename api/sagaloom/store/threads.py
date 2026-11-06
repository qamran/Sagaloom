import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ThreadKind = Literal["chat", "import"]

_COLUMNS = ("thread_id", "world_id", "created_at", "title", "kind")
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM threads"


class ThreadInfo(BaseModel):
    thread_id: str
    world_id: str
    created_at: str
    title: str | None = None
    kind: ThreadKind = "chat"


def _info(row: tuple) -> ThreadInfo:
    return ThreadInfo(**dict(zip(_COLUMNS, row)))


class ThreadRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS threads ("
            "thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT, kind TEXT NOT NULL DEFAULT 'chat')"
        )
        # An M1 table has no `kind`: every thread then was a chat.
        if "kind" not in {row[1] for row in conn.execute("PRAGMA table_info(threads)")}:
            conn.execute("ALTER TABLE threads ADD COLUMN kind TEXT NOT NULL DEFAULT 'chat'")
            conn.commit()
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

    def delete(self, thread_id: str) -> None:
        """Removes the registry row only (the checkpoint stays). Unknown ids are a no-op."""
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
