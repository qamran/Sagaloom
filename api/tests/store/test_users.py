import sqlite3
from datetime import UTC, datetime, timedelta

from sagaloom.store.users import UserRegistry, admin_flag


def _reg(tmp_path):
    return UserRegistry(tmp_path / "users.sqlite")


def test_upsert_then_get(tmp_path):
    reg = _reg(tmp_path)
    assert reg.get("user_1") is None
    created = reg.upsert_profile("user_1", email="A@x.io", email_verified=True, display_name="Ann")
    assert reg.get("user_1") == created
    assert created.last_world_id is None and created.is_admin is False
    updated = reg.upsert_profile("user_1", email="a@x.io", email_verified=False, display_name="Ann B")
    assert updated.display_name == "Ann B" and updated.email_verified is False
    assert updated.created_at == created.created_at
    assert updated.profile_checked_at >= created.profile_checked_at


def test_email_lowercased(tmp_path):
    reg = _reg(tmp_path)
    user = reg.upsert_profile("user_1", email="Ann@X.io", email_verified=True, display_name="Ann")
    assert user.email == "ann@x.io"
    assert reg.find_by_email("ANN@x.IO") == user
    assert reg.find_by_email("nobody@x.io") is None


def test_two_users_may_share_an_email_find_takes_newest_verified(tmp_path):
    reg = _reg(tmp_path)
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    old = reg.upsert_profile("u1", email="ann@x.io", email_verified=True, display_name="A", checked_at=t0)
    new = reg.upsert_profile(
        "u2", email="ann@x.io", email_verified=True, display_name="B", checked_at=t0 + timedelta(hours=1)
    )
    reg.upsert_profile(
        "u3", email="ann@x.io", email_verified=False, display_name="C", checked_at=t0 + timedelta(hours=2)
    )
    assert reg.get("u1") == old
    assert reg.find_by_email("ann@x.io") == new  # u3 is newer but unverified
    assert new.profile_checked_at == (t0 + timedelta(hours=1)).isoformat()


def test_unique_email_table_from_an_earlier_schema_is_rebuilt(tmp_path):
    path = tmp_path / "users.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
        "email_verified INTEGER NOT NULL, display_name TEXT NOT NULL, last_world_id TEXT, "
        "created_at TEXT NOT NULL, profile_checked_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO users VALUES ('u1', 'ann@x.io', 1, 'Ann', 'velmar', '2026-11-01', '2026-11-01')"
    )
    conn.commit()
    conn.close()
    reg = UserRegistry(path)
    assert reg.get("u1").last_world_id == "velmar"
    reg.upsert_profile("u2", email="ann@x.io", email_verified=True, display_name="Other")
    assert reg.get("u2").email == "ann@x.io"
    with sqlite3.connect(path) as c:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    assert names == ["users"]


def test_set_last_world(tmp_path):
    reg = _reg(tmp_path)
    reg.upsert_profile("user_1", email="a@x.io", email_verified=True, display_name="Ann")
    reg.set_last_world("user_1", "velmar")
    assert reg.get("user_1").last_world_id == "velmar"
    reg.set_last_world("user_1", None)
    assert reg.get("user_1").last_world_id is None


def test_admin_flag_needs_verified_matching_email(tmp_path):
    reg = _reg(tmp_path)
    verified = reg.upsert_profile("u1", email="Boss@x.io", email_verified=True, display_name="B")
    unverified = reg.upsert_profile("u2", email="boss2@x.io", email_verified=False, display_name="C")
    assert admin_flag(verified, "boss@X.io") is True
    assert admin_flag(verified, "  boss@x.io	") is True  # whitespace around ADMIN_EMAIL
    assert admin_flag(verified, None) is False
    assert admin_flag(verified, "other@x.io") is False
    assert admin_flag(unverified, "boss2@x.io") is False
