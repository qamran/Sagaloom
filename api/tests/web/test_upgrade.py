"""The M4 -> M5 upgrade, end to end (M5 spec §7): a data dir from before accounts (legacy-keyed
canon records, an ownerless world, prompt records without a user) -> app start -> the admin's
first verified request. Nothing is lost, and the migration runs before any store write."""

import sqlite3

from httpx import ASGITransport, AsyncClient

from fakes import HEADERS
from sagaloom.auth import ClerkProfile
from sagaloom.config import Settings
from sagaloom.models import Entry
from sagaloom.promptlog import PromptLog, PromptRecord
from sagaloom.store.canon import norm
from sagaloom.store.threads import ThreadRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.app import SEED_DIR, AppDeps, create_app
from stubs import FakeDirectory, FakeVerifier, bearer

BOSS = "boss@example.test"
LEGACY = [("ent_0001", "Old Harbour"), ("ent_0002", "Lantern Quay")]


def _legacy_canon(store) -> list[Entry]:
    """Records as stored before ids were per world: record id == entry id, no `entry_id`."""
    entries = [Entry(id=i, world_id="velmar", title=t, type="place", body="Kept.") for i, t in LEGACY]
    docs = [f"{e.title}\n\n{e.body}" for e in entries]
    store.col.upsert(
        ids=[e.id for e in entries],
        documents=docs,
        embeddings=store.embeddings.embed_documents(docs),
        metadatas=[
            {"world_id": e.world_id, "type": e.type, "status": e.status,
             "title_norm": norm(e.title), "entry_json": e.model_dump_json()}
            for e in entries
        ],
    )
    return entries


def _legacy_prompt_log(path, thread_id: str) -> None:
    """The M4 `prompt_log` table (no `user_id` column) with one call of 0.25 US$."""
    rec = PromptRecord(
        id="m4-call", thread_id=thread_id, run_id="r", provider="openrouter", model="m", role="agent",
        request={"messages": [], "tools": []},
        response={"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.25},
        started_at="2026-10-01T12:00:00+00:00",
    )
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE prompt_log (id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, "
            "run_id TEXT NOT NULL, started_at TEXT NOT NULL, record TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO prompt_log VALUES (?, ?, ?, ?, ?)",
            (rec.id, rec.thread_id, rec.run_id, rec.started_at, rec.model_dump_json()),
        )
    conn.close()


def _record_order(store, events: list[str]) -> None:
    """Logs the migration and every canon write, in order."""
    for name in ("migrate_record_ids", "upsert_entry", "upsert_entries", "delete_entry"):
        real = getattr(store, name)

        def wrapped(*a, _real=real, _name=name, **kw):
            events.append(_name)
            return _real(*a, **kw)

        setattr(store, name, wrapped)


async def test_m4_data_dir_upgrades_to_the_admin(store, tmp_path):
    entries = _legacy_canon(store)
    worlds = WorldRegistry(tmp_path / "worlds.json")
    worlds.create("Velmar", world_id="velmar", is_demo=True)  # ownerless, as before M5
    threads = ThreadRegistry(tmp_path / "threads.sqlite")
    tid = threads.create("velmar")
    _legacy_prompt_log(tmp_path / "prompts.sqlite", tid)
    events: list[str] = []
    _record_order(store, events)

    settings = Settings(
        _env_file=None, openrouter_api_key="k", api_shared_secret="test-secret", data_dir=tmp_path,
        admin_email=BOSS,
    )
    deps = AppDeps(
        store=store, graph="graph", worlds=worlds, threads=threads,
        promptlog=PromptLog(tmp_path / "prompts.sqlite"),
        verifier=FakeVerifier({"tok-boss": "user_boss", "tok-new": "user_new"}),
        directory=FakeDirectory({"user_boss": ClerkProfile(email=BOSS, email_verified=True, display_name="Boss")}),
        seed_dir=SEED_DIR,
    )
    app = create_app(settings, deps)
    async with app.router.lifespan_context(app):
        assert events == ["migrate_record_ids"]  # at start: the migration, and no write yet
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            boss = {**HEADERS, **bearer("tok-boss")}
            r = await c.get("/api/worlds", headers=boss)
            assert r.status_code == 200 and [w["id"] for w in r.json()] == ["velmar"]
            assert worlds.get("velmar").owner_id == "user_boss"
            assert len(worlds.all_worlds()) == 1  # the admin took the old Velmar: no second copy
            r = await c.get("/api/worlds/velmar/entries", headers=boss)
            assert r.json() == [e.model_dump(mode="json") for e in entries]  # ids unchanged
            r = await c.get("/api/worlds/velmar/entries/ent_0002", headers=boss)
            assert r.status_code == 200 and r.json()["title"] == "Lantern Quay"
            assert (await c.get(f"/api/threads/{tid}/llm-log", headers=boss)).status_code == 200
            # A new account after the upgrade: its own Velmar under a fresh id, written after
            # the migration.
            r = await c.get("/api/worlds", headers={**HEADERS, **bearer("tok-new")})
            [new] = r.json()
            assert new["id"] != "velmar"
    assert deps.promptlog.usage(user_id="user_boss").cost_usd == 0.25  # the legacy cost is the admin's
    assert deps.promptlog.usage(user_id="user_new").cost_usd == 0
    assert events[0] == "migrate_record_ids" and "upsert_entries" in events
    assert store.col.get(ids=[i for i, _ in LEGACY], include=[])["ids"] == []  # no legacy keys left
