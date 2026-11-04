import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class ThreadInfo(BaseModel):
    thread_id: str
    world_id: str
    created_at: str
    title: str | None = None


class ThreadRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS threads ("
            "thread_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, "
            "created_at TEXT NOT NULL, title TEXT)"
        )
        return conn

    def create(self, world_id: str) -> str:
        thread_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO threads (thread_id, world_id, created_at) VALUES (?, ?, ?)",
                (thread_id, world_id, datetime.now(UTC).isoformat()),
            )
        return thread_id

    def get(self, thread_id: str) -> ThreadInfo | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT thread_id, world_id, created_at, title FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return ThreadInfo(**dict(zip(("thread_id", "world_id", "created_at", "title"), row))) if row else None

    def list(self, world_id: str | None = None) -> list[ThreadInfo]:
        sql = "SELECT thread_id, world_id, created_at, title FROM threads"
        args: tuple = ()
        if world_id is not None:
            sql += " WHERE world_id = ?"
            args = (world_id,)
        with closing(self._connect()) as conn:
            rows = conn.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        return [ThreadInfo(**dict(zip(("thread_id", "world_id", "created_at", "title"), r))) for r in rows]
