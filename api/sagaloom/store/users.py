import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sagaloom.models import User

_COLUMNS = (
    "id",
    "email",
    "email_verified",
    "display_name",
    "last_world_id",
    "created_at",
    "profile_checked_at",
)
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM users"


def _user(row: tuple) -> User:
    data = dict(zip(_COLUMNS, row))
    data["email_verified"] = bool(data["email_verified"])
    return User(**data)


def admin_flag(user: User, admin_email: str | None) -> bool:
    """Admin = a Clerk-verified email equal to `admin_email`, case-insensitively."""
    return bool(
        admin_email and user.email_verified and user.email.casefold() == admin_email.strip().casefold()
    )


class UserRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._ready = False
        self._ready_lock = threading.Lock()  # sync routes run in a thread pool

    def _connect(self) -> sqlite3.Connection:
        """A connection to a table that exists. The schema is created once per registry."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        if not self._ready:
            with self._ready_lock:
                if not self._ready:
                    try:
                        conn.execute(
                            "CREATE TABLE IF NOT EXISTS users ("
                            "id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
                            "email_verified INTEGER NOT NULL, display_name TEXT NOT NULL, "
                            "last_world_id TEXT, created_at TEXT NOT NULL, "
                            "profile_checked_at TEXT NOT NULL)"
                        )
                        conn.commit()
                    except BaseException:
                        conn.close()
                        raise
                    self._ready = True
        return conn

    def get(self, user_id: str) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(_SELECT + " WHERE id = ?", (user_id,)).fetchone()
        return _user(row) if row else None

    def find_by_email(self, email: str) -> User | None:
        with closing(self._connect()) as conn:
            row = conn.execute(_SELECT + " WHERE email = ?", (email.casefold(),)).fetchone()
        return _user(row) if row else None

    def upsert_profile(
        self, user_id: str, *, email: str, email_verified: bool, display_name: str
    ) -> User:
        """Creates the user or refreshes their profile; stamps `profile_checked_at`. Raises
        `ValueError` if another user already holds this email."""
        now = datetime.now(UTC).isoformat()
        values = (email.casefold(), int(email_verified), display_name, now)
        try:
            with closing(self._connect()) as conn, conn:
                cur = conn.execute(
                    "UPDATE users SET email = ?, email_verified = ?, display_name = ?, "
                    "profile_checked_at = ? WHERE id = ?",
                    (*values, user_id),
                )
                if cur.rowcount == 0:
                    conn.execute(
                        "INSERT INTO users (email, email_verified, display_name, profile_checked_at, "
                        "id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (*values, user_id, now),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Email {email!r} belongs to another user") from exc
        user = self.get(user_id)
        assert user is not None
        return user

    def set_last_world(self, user_id: str, world_id: str | None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("UPDATE users SET last_world_id = ? WHERE id = ?", (world_id, user_id))
