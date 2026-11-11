import pytest

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


def test_email_lowercased_and_unique(tmp_path):
    reg = _reg(tmp_path)
    user = reg.upsert_profile("user_1", email="Ann@X.io", email_verified=True, display_name="Ann")
    assert user.email == "ann@x.io"
    assert reg.find_by_email("ANN@x.IO") == user
    assert reg.find_by_email("nobody@x.io") is None
    with pytest.raises(ValueError):
        reg.upsert_profile("user_2", email="ann@x.io", email_verified=True, display_name="Other")


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
    assert admin_flag(verified, None) is False
    assert admin_flag(verified, "other@x.io") is False
    assert admin_flag(unverified, "boss2@x.io") is False
