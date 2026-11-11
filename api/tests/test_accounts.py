"""Account provisioning (M5, spec §5.4): each user's own Velmar, the admin, profile refreshes."""

import asyncio
import logging
import re
import threading
from datetime import UTC, datetime, timedelta

import pytest

from sagaloom.accounts import ensure_user
from sagaloom.auth import AuthError, Claims, ClerkProfile
from sagaloom.config import Settings
from sagaloom.seed import VELMAR_ID, copy_velmar, load_seed
from sagaloom.store.users import UserRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.app import SEED_DIR, AppDeps, create_app
from stubs import FakeDirectory

BOSS = "boss@example.test"


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw) -> None:
        self.t += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def deps(store, tmp_path, clock):
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    return AppDeps(
        store=store,
        worlds=WorldRegistry(tmp_path / "worlds.json"),
        users=UserRegistry(tmp_path / "users.sqlite"),
        settings=settings,
        directory=FakeDirectory(),
        seed_dir=SEED_DIR,
        now=clock,
    )


def profile(email, verified=True, name="Someone"):
    return ClerkProfile(email=email, email_verified=verified, display_name=name)


def as_admin(deps, sub="user_boss", verified=True):
    deps.settings.admin_email = BOSS
    deps.directory.profiles[sub] = profile(BOSS, verified)


async def test_new_user_gets_own_velmar_with_readme_ids(deps, store):
    a = await ensure_user(deps, Claims(sub="user_a"))
    b = await ensure_user(deps, Claims(sub="user_b"))
    [wa] = deps.worlds.owned_by("user_a")
    [wb] = deps.worlds.owned_by("user_b")
    assert wa.id != wb.id
    assert wa.is_demo and wb.is_demo and wa.name == wb.name == "Velmar"
    assert a.last_world_id == wa.id and b.last_world_id == wb.id
    assert deps.users.get("user_a").last_world_id == wa.id
    for w in (wa, wb):
        assert store.get_entry(w.id, "ent_0012").title == "Ister, the red moon"
        assert store.get_entry(w.id, "ent_0007").title == "Sky of Velmar"
        assert len(store.list_entries(w.id)) == 19


async def test_change_in_one_velmar_not_in_other(deps, store):
    await ensure_user(deps, Claims(sub="user_a"))
    await ensure_user(deps, Claims(sub="user_b"))
    [wa] = deps.worlds.owned_by("user_a")
    [wb] = deps.worlds.owned_by("user_b")
    sky = store.get_entry(wa.id, "ent_0007")
    store.upsert_entry(sky.model_copy(update={"body": "Three moons now."}))
    assert store.get_entry(wa.id, "ent_0007").body == "Three moons now."
    assert store.get_entry(wb.id, "ent_0007").body != "Three moons now."


async def test_admin_inherits_unowned_worlds(deps, store):
    load_seed(store, deps.worlds, SEED_DIR)  # the legacy global Velmar, no owner
    mine = deps.worlds.create("Author's world")
    ids_before = [e.id for e in store.list_entries(VELMAR_ID)]
    as_admin(deps)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is True
    assert sorted(w.id for w in deps.worlds.owned_by("user_boss")) == sorted([VELMAR_ID, mine.id])
    assert len(deps.worlds.all_worlds()) == 2  # no second copy
    assert [e.id for e in store.list_entries(VELMAR_ID)] == ids_before


async def test_non_admin_first_user_gets_nothing_unowned(deps, store):
    load_seed(store, deps.worlds, SEED_DIR)
    deps.settings.admin_email = BOSS
    a = await ensure_user(deps, Claims(sub="user_a"))
    assert a.is_admin is False
    assert deps.worlds.get(VELMAR_ID).owner_id is None
    [own] = deps.worlds.owned_by("user_a")
    assert own.id != VELMAR_ID


async def test_unverified_admin_email_gets_nothing(deps, store):
    load_seed(store, deps.worlds, SEED_DIR)
    as_admin(deps, verified=False)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is False
    assert deps.worlds.get(VELMAR_ID).owner_id is None


async def test_admin_promoted_after_verification(deps, store, clock):
    load_seed(store, deps.worlds, SEED_DIR)
    as_admin(deps, verified=False)
    assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is False
    deps.directory.profiles["user_boss"] = profile(BOSS, verified=True)
    clock.advance(minutes=9)
    assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is False  # not yet re-checked
    assert deps.worlds.get(VELMAR_ID).owner_id is None
    clock.advance(minutes=2)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is True
    assert deps.worlds.get(VELMAR_ID).owner_id == "user_boss"


async def test_verified_profile_refreshed_after_24_hours(deps, clock):
    """An admin whose Clerk email moved away from ADMIN_EMAIL loses admin at the daily refresh."""
    as_admin(deps)
    assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is True
    deps.directory.profiles["user_boss"] = profile("someone.else@example.test")
    clock.advance(hours=23)
    assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is True
    assert deps.directory.fetched == ["user_boss"]
    clock.advance(hours=1, seconds=1)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is False and boss.email == "someone.else@example.test"
    assert deps.directory.fetched == ["user_boss", "user_boss"]


async def test_admin_email_with_whitespace_still_matches(deps):
    as_admin(deps)
    deps.settings.admin_email = f"  {BOSS.upper()} \t"
    assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is True


async def test_two_clerk_ids_with_the_same_email_both_work(deps):
    deps.directory.profiles["user_old"] = profile("shared@example.test")
    deps.directory.profiles["user_new"] = profile("shared@example.test")
    old = await ensure_user(deps, Claims(sub="user_old"))
    new = await ensure_user(deps, Claims(sub="user_new"))
    assert old.email == new.email == "shared@example.test"
    assert old.id != new.id


async def test_refresh_failure_keeps_the_stored_profile(deps, clock, caplog):
    as_admin(deps)
    await ensure_user(deps, Claims(sub="user_boss"))

    class Down:
        async def fetch(self, user_id):
            raise AuthError("Clerk lookup failed: ConnectError")

    deps.directory = Down()
    clock.advance(hours=25)
    caplog.set_level(logging.WARNING)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is True and boss.email == BOSS
    assert "Clerk lookup failed: ConnectError" in caplog.text
    deps.directory = None  # no secret key: a due refresh is skipped the same way
    assert (await ensure_user(deps, Claims(sub="user_boss"))).email == BOSS


async def test_new_user_without_clerk_is_an_auth_error(deps):
    deps.directory = None
    with pytest.raises(AuthError):
        await ensure_user(deps, Claims(sub="user_a"))
    assert deps.users.get("user_a") is None


async def test_concurrent_first_requests_seed_once(deps):
    users = await asyncio.gather(*(ensure_user(deps, Claims(sub="user_a")) for _ in range(5)))
    [world] = deps.worlds.owned_by("user_a")
    assert {u.last_world_id for u in users} == {world.id}
    assert len(deps.worlds.all_worlds()) == 1
    assert deps.directory.fetched == ["user_a"]


async def test_fresh_user_skips_the_lock(deps):
    await ensure_user(deps, Claims(sub="user_a"))

    class NoLocks:
        def hold(self, key):
            raise AssertionError("the lock was taken for a fresh, provisioned user")

    deps.user_locks = NoLocks()
    assert (await ensure_user(deps, Claims(sub="user_a"))).id == "user_a"


async def test_user_left_without_a_world_is_provisioned_on_the_next_request(deps, store):
    store.embeddings = Embedder(store.embeddings, fail=1)
    with pytest.raises(RuntimeError):
        await ensure_user(deps, Claims(sub="user_a"))
    assert deps.worlds.all_worlds() == []
    a = await ensure_user(deps, Claims(sub="user_a"))
    [world] = deps.worlds.owned_by("user_a")
    assert a.last_world_id == world.id and len(store.list_entries(world.id)) == 19


async def test_admin_email_set_later_assigns_on_the_next_request(deps, store):
    deps.directory.profiles["user_boss"] = profile(BOSS)
    await ensure_user(deps, Claims(sub="user_boss"))
    legacy = deps.worlds.create("Legacy")
    deps.settings.admin_email = BOSS
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin is True
    assert deps.worlds.get(legacy.id).owner_id == "user_boss"


class Embedder:
    """Wraps embeddings: records each `embed_documents` batch size; the first `fail` calls raise
    (the provider down)."""

    def __init__(self, inner, fail: int = 0):
        self.inner, self.fail, self.batches = inner, fail, []

    def embed_documents(self, texts):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("embedding provider unavailable")
        self.batches.append(len(texts))
        return self.inner.embed_documents(texts)

    def embed_query(self, text):
        return self.inner.embed_query(text)


def test_copy_velmar_failure_leaves_no_world_or_entries(store, tmp_path):
    worlds = WorldRegistry(tmp_path / "worlds.json")
    store.embeddings = Embedder(store.embeddings, fail=1)
    with pytest.raises(RuntimeError):
        copy_velmar(store, worlds, SEED_DIR, "user_a")
    assert worlds.all_worlds() == []
    assert store.list_entries(VELMAR_ID) == []
    # A failure after the entries are written (the world record) deletes them again.
    real_create = worlds.create
    worlds.create = lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full"))
    with pytest.raises(OSError):
        copy_velmar(store, worlds, SEED_DIR, "user_a")
    assert store.list_entries(VELMAR_ID) == [] and not store.has_world(VELMAR_ID)
    worlds.create = real_create
    world = copy_velmar(store, worlds, SEED_DIR, "user_a")
    assert world.id == VELMAR_ID and world.owner_id == "user_a" and world.is_demo
    assert len(store.list_entries(world.id)) == 19


async def test_startup_assigns_nothing_and_creates_no_world(store, tmp_path, caplog):
    """Spec §5.4 (ruling): unowned worlds go to the admin only inside `ensure_user`; startup no
    longer seeds a global Velmar. It warns once when ADMIN_EMAIL is unset."""
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    worlds = WorldRegistry(tmp_path / "worlds.json")
    users = UserRegistry(tmp_path / "users.sqlite")
    worlds.create("Legacy")
    users.upsert_profile("user_boss", email=BOSS, email_verified=True, display_name="Boss")
    deps = AppDeps(store=store, graph="graph", worlds=worlds, users=users, directory=FakeDirectory())
    app = create_app(settings, deps)
    caplog.set_level(logging.WARNING)
    async with app.router.lifespan_context(app):
        pass
    assert [(w.id, w.owner_id) for w in worlds.all_worlds()] == [("legacy", None)]
    assert [r for r in caplog.records if "ADMIN_EMAIL" in r.getMessage()][0].levelno == logging.WARNING
    settings.admin_email = BOSS
    caplog.clear()
    async with app.router.lifespan_context(app):
        pass
    assert worlds.get("legacy").owner_id is None
    assert "ADMIN_EMAIL" not in caplog.text


async def test_startup_migrates_record_ids_first(store, tmp_path, monkeypatch):
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    calls = []
    monkeypatch.setattr(store, "migrate_record_ids", lambda: calls.append("migrate") or 0)
    deps = AppDeps(store=store, graph="graph", directory=FakeDirectory())
    app = create_app(settings, deps)
    async with app.router.lifespan_context(app):
        pass
    assert calls == ["migrate"]


class CountingDown:
    """A Clerk that fails every lookup (after `delay` seconds) and counts them."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = 0

    async def fetch(self, user_id):
        self.calls += 1
        await asyncio.sleep(self.delay)
        raise AuthError("Clerk lookup failed: ReadTimeout")


async def test_failed_refresh_backs_off_for_a_minute(deps, clock):
    as_admin(deps)
    await ensure_user(deps, Claims(sub="user_boss"))
    down = CountingDown()
    deps.directory = down
    clock.advance(hours=25)
    for _ in range(2):
        assert (await ensure_user(deps, Claims(sub="user_boss"))).is_admin is True
    assert down.calls == 1
    clock.advance(seconds=59)
    await ensure_user(deps, Claims(sub="user_boss"))
    assert down.calls == 1
    clock.advance(seconds=2)
    await ensure_user(deps, Claims(sub="user_boss"))
    assert down.calls == 2


async def test_slow_failing_refresh_is_tried_once_by_parallel_requests(deps, clock):
    as_admin(deps)
    await ensure_user(deps, Claims(sub="user_boss"))
    down = CountingDown(delay=0.05)
    deps.directory = down
    clock.advance(hours=25)
    users = await asyncio.gather(*(ensure_user(deps, Claims(sub="user_boss")) for _ in range(4)))
    assert all(u.is_admin for u in users)
    assert down.calls == 1


async def test_cancelled_first_request_still_leaves_one_velmar(deps, store):
    started, go = threading.Event(), threading.Event()
    real = store.upsert_entries

    def slow(entries):
        started.set()
        go.wait(5)
        return real(entries)

    store.upsert_entries = slow
    first = asyncio.create_task(ensure_user(deps, Claims(sub="user_a")))
    while not started.is_set():
        await asyncio.sleep(0.01)
    first.cancel()
    second = asyncio.create_task(ensure_user(deps, Claims(sub="user_a")))
    await asyncio.sleep(0.05)
    go.set()
    a = await second
    with pytest.raises(asyncio.CancelledError):
        await first
    [world] = deps.worlds.owned_by("user_a")
    assert len(deps.worlds.all_worlds()) == 1 and a.last_world_id == world.id


async def test_naive_profile_timestamp_is_read_as_utc(deps, clock):
    deps.users.upsert_profile(
        "user_a", email="a@example.test", email_verified=True, display_name="A",
        checked_at=clock().replace(tzinfo=None),
    )
    await ensure_user(deps, Claims(sub="user_a"))
    assert deps.directory.fetched == []  # fresh, not a TypeError
    clock.advance(hours=25)
    await ensure_user(deps, Claims(sub="user_a"))
    assert deps.directory.fetched == ["user_a"]


async def test_startup_backfills_prompt_log_user_ids(store, tmp_path):
    """Spec §5.2: prompt records from before M5 get the owner of their thread's world at start;
    a record whose thread is gone stays ownerless."""
    from sagaloom.promptlog import PromptLog, PromptRecord
    from sagaloom.store.threads import ThreadRegistry

    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    worlds = WorldRegistry(tmp_path / "worlds.json")
    worlds.create("Mine", world_id="mine", owner_id="user_a")
    threads = ThreadRegistry(tmp_path / "threads.sqlite")
    tid = threads.create("mine")
    log = PromptLog(tmp_path / "prompts.sqlite")
    for id, thread_id in (("kept", tid), ("orphan", "gone")):
        log.add(
            PromptRecord(
                id=id, thread_id=thread_id, run_id="r", provider="openrouter", model="m",
                request={"messages": [], "tools": []},
                response={"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.5},
                started_at="2026-11-01T00:00:00+00:00",
            )
        )
    assert log.usage(user_id="user_a").cost_usd == 0
    deps = AppDeps(store=store, graph="graph", worlds=worlds, threads=threads, promptlog=log, directory=FakeDirectory())
    app = create_app(settings, deps)
    async with app.router.lifespan_context(app):
        pass
    assert log.usage(user_id="user_a").cost_usd == 0.5
    assert log.usage().cost_usd == 1.0


async def test_admin_first_request_takes_legacy_costs(deps, store, tmp_path):
    """Spec §5.2: pre-M5 prompt records of an ownerless world become the admin's cost when the
    admin takes the world on their first request, without waiting for a restart."""
    from sagaloom.promptlog import PromptLog, PromptRecord
    from sagaloom.store.threads import ThreadRegistry

    deps.threads = ThreadRegistry(tmp_path / "threads.sqlite")
    deps.promptlog = PromptLog(tmp_path / "prompts.sqlite")
    legacy = deps.worlds.create("Legacy")  # no owner, as before M5
    tid = deps.threads.create(legacy.id)
    for id, thread_id in (("legacy-call", tid), ("orphan", "gone")):
        deps.promptlog.add(
            PromptRecord(
                id=id, thread_id=thread_id, run_id="r", provider="openrouter", model="m",
                request={"messages": [], "tools": []},
                response={"prompt_tokens": 1, "completion_tokens": 1, "cost_usd": 0.5},
                started_at="2026-11-01T00:00:00+00:00",
            )
        )
    assert deps.promptlog.backfill_user_ids(lambda t: None) == 0  # startup: nobody owns it yet
    await ensure_user(deps, Claims(sub="user_a"))  # a non-admin takes nothing
    assert deps.promptlog.usage(user_id="user_a").cost_usd == 0
    as_admin(deps)
    await ensure_user(deps, Claims(sub="user_boss"))
    assert deps.worlds.get(legacy.id).owner_id == "user_boss"
    assert deps.promptlog.usage(user_id="user_boss").cost_usd == 0.5
    assert deps.promptlog.usage().cost_usd == 1.0  # the gone thread's call stays nobody's


async def test_failed_backfill_after_takeover_does_not_fail_the_request(deps, tmp_path, caplog):
    """The takeover stands even if the prompt-log backfill fails; startup backfill retries it."""
    from sagaloom.promptlog import PromptLog
    from sagaloom.store.threads import ThreadRegistry

    class BrokenLog(PromptLog):
        def backfill_user_ids(self, owner_of_thread):
            raise RuntimeError("database is locked")

    deps.threads = ThreadRegistry(tmp_path / "threads.sqlite")
    deps.promptlog = BrokenLog(tmp_path / "prompts.sqlite")
    legacy = deps.worlds.create("Legacy")
    as_admin(deps)
    caplog.set_level(logging.WARNING)
    boss = await ensure_user(deps, Claims(sub="user_boss"))
    assert boss.is_admin and deps.worlds.get(legacy.id).owner_id == "user_boss"
    assert "database is locked" in caplog.text


def test_copy_velmar_embeds_in_one_call(store, tmp_path):
    worlds = WorldRegistry(tmp_path / "worlds.json")
    store.embeddings = Embedder(store.embeddings)
    world = copy_velmar(store, worlds, SEED_DIR, "user_a")
    assert store.embeddings.batches == [19] and len(store.list_entries(world.id)) == 19


def test_copy_velmar_skips_an_id_with_records_left(store, tmp_path):
    """A lost worlds.json: records under `velmar` remain, so a new account must not get them."""
    from sagaloom.models import Entry

    store.upsert_entry(Entry(id="ent_0001", world_id=VELMAR_ID, title="Old", type="place", body="x"))
    worlds = WorldRegistry(tmp_path / "worlds.json")
    world = copy_velmar(store, worlds, SEED_DIR, "user_a")
    assert re.fullmatch(r"velmar-[a-z0-9]{4}", world.id), world.id
    assert store.get_entry(VELMAR_ID, "ent_0001").title == "Old"
    assert len(store.list_entries(world.id)) == 19


def test_copy_velmar_failed_chroma_write_leaves_no_entries(store, tmp_path):
    """A write that fails after embedding (part of the batch may have landed) is cleaned up."""
    worlds = WorldRegistry(tmp_path / "worlds.json")
    real = store.col.upsert
    calls = []

    def half_then_fail(**kw):
        calls.append(len(kw["ids"]))
        real(**{k: v[:5] for k, v in kw.items()})  # some records land, then the write fails
        raise RuntimeError("chroma write failed")

    store.col.upsert = half_then_fail
    with pytest.raises(RuntimeError):
        copy_velmar(store, worlds, SEED_DIR, "user_a")
    store.col.upsert = real
    assert calls == [19]
    assert worlds.all_worlds() == [] and not store.has_world(VELMAR_ID)
