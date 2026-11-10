"""R15: the runtime saver rebuilds our types without warnings, with an explicit allowlist."""

import logging
import warnings

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from langchain_core.messages import AIMessage

from sagaloom.config import Settings
from sagaloom.graph.build import run_config, sqlite_checkpointer

from sagaloom.models import Usage

from test_graph import W, create_call, make, only_pid, resume, run, start


async def test_runtime_checkpointer_roundtrips_models_without_warnings(store, tmp_path, caplog):
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    cfg = run_config("t1", W)
    caplog.set_level(logging.WARNING)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        async with sqlite_checkpointer(settings) as saver:
            assert isinstance(saver, AsyncSqliteSaver)
            graph, *_ = make(store, [create_call()], saver=saver)
            await run(graph, start(), cfg)
        async with sqlite_checkpointer(settings) as saver:  # fresh process-like reload
            graph, *_ = make(store, [], saver=saver)
            values = (await graph.aget_state(cfg)).values
            [p] = values["pending_proposals"]
            assert p.after.title == "Ostra" and "token_usage" not in values
            assert await only_pid(graph, cfg) == p.proposal_id
    assert not [r for r in caplog.records if "msgpack" in r.getMessage().lower() or "unregistered" in r.getMessage().lower()], caplog.text


async def test_old_checkpoint_with_token_usage_channel_still_loads(store, tmp_path):
    """M1 checkpoints carry a `token_usage` channel the schema no longer has (it was dropped
    when the prompt log became the only usage source)."""
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    cfg = run_config("t-old", W)
    async with sqlite_checkpointer(settings) as saver:
        graph, *_ = make(store, [AIMessage(content="one"), AIMessage(content="two")], saver=saver)
        await run(graph, start("hi"), cfg)
        tup = await saver.aget_tuple(cfg)
        cp = {**tup.checkpoint, "channel_values": {**tup.checkpoint["channel_values"], "token_usage": Usage()}}
        version = saver.get_next_version(max(cp["channel_versions"].values()), None)
        cp["channel_versions"] = {**cp["channel_versions"], "token_usage": version}
        await saver.aput(tup.config, cp, tup.metadata, {"token_usage": version})
        assert "token_usage" in (await saver.aget_tuple(cfg)).checkpoint["channel_values"]
        assert await run(graph, start("again"), cfg) == ["guard", "router", "agent"]
        assert (await graph.aget_state(cfg)).values["messages"][-1].content == "two"


async def test_blocked_turn_roundtrips_through_the_strict_saver(store, tmp_path, caplog):
    """The guard's write (RemoveMessage + its notice) survives the runtime saver's strict serde."""
    from sagaloom.guard import BLOCK_COPY, GuardVerdict

    from test_graph import StubLLM

    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", data_dir=tmp_path)
    cfg = run_config("t-blocked", W)
    caplog.set_level(logging.WARNING)
    verdicts = iter([GuardVerdict(verdict="unsafe", reason="x"), GuardVerdict(verdict="safe", reason="ok")])
    guard = StubLLM(lambda _: next(verdicts))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        async with sqlite_checkpointer(settings) as saver:
            graph, *_ = make(store, [], saver=saver, guard=guard)
            assert await run(graph, start("bad"), cfg) == ["guard"]
        async with sqlite_checkpointer(settings) as saver:
            graph, *_ = make(store, [AIMessage(content="ok")], saver=saver, guard=guard)
            [notice] = (await graph.aget_state(cfg)).values["messages"]
            assert isinstance(notice, AIMessage) and notice.name == "guard"
            assert notice.content == BLOCK_COPY["unsafe"]
            assert await run(graph, start("How many moons?"), cfg) == ["guard", "router", "agent"]
    assert not [r for r in caplog.records if "msgpack" in r.getMessage().lower() or "unregistered" in r.getMessage().lower()], caplog.text


def test_memory_models_roundtrip_through_the_strict_serde(caplog):
    from sagaloom.graph.build import checkpoint_serde
    from sagaloom.models import MemoryResult, MemoryUpdate

    serde = checkpoint_serde()
    for obj in (
        [MemoryUpdate(key="tone", value="grim")],
        MemoryResult(
            key="tone", value="grim", stored=True, note="Remembered: tone → grim", reason="stored"
        ),
    ):
        assert serde.loads_typed(serde.dumps_typed(obj)) == obj
    assert "not in the allowed" not in caplog.text.lower() and "blocked" not in caplog.text.lower()


def test_proposal_imported_flag_roundtrips_and_defaults_false(caplog):
    """`Proposal.imported` survives the strict serde; a pending proposal from a checkpoint written
    before the field existed has no `imported` key and reads as False (a myth save restores the body)."""
    from sagaloom.graph.build import checkpoint_serde
    from sagaloom.models import Proposal

    serde = checkpoint_serde()
    p = Proposal(proposal_id="p1", action="create", world_id=W, entry_id=None, before=None, after=None, imported=True)
    assert serde.loads_typed(serde.dumps_typed([p])) == [p]
    old = p.model_dump(mode="json")
    del old["imported"]
    assert Proposal.model_validate(old).imported is False
    assert "not in the allowed" not in caplog.text.lower() and "blocked" not in caplog.text.lower()


SAVERS = ("InMemorySaver", "MemorySaver", "AsyncSqliteSaver", "SqliteSaver")


def test_every_test_checkpointer_uses_the_strict_serde(caplog):
    """Every checkpointer built under api/tests passes a serde (they all go through
    `checkpointers.memory_checkpointer` or `sqlite_checkpointer`), and the in-memory one
    rebuilds `Proposal`/`CheckResult` without langgraph's "Deserializing unregistered type"
    warning. An AST scan, so a call that
    wraps onto several lines is still seen."""
    import ast
    from pathlib import Path

    from checkpointers import memory_checkpointer

    from sagaloom.models import CheckResult, EntryDraft, EntrySource, Proposal

    tests_dir = Path(__file__).resolve().parents[1]
    bare = []
    for f in tests_dir.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text("utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            # `from_conn_string` takes no serde, so it always builds a permissive saver.
            if name == "from_conn_string" or (
                name in SAVERS and not any(k.arg == "serde" for k in node.keywords)
            ):
                bare.append(f"{f.relative_to(tests_dir)}:{node.lineno}")
    assert not bare, bare

    serde = memory_checkpointer().serde
    draft = EntryDraft(
        title="Ostra", type="place", body="A port.", trusted=False,
        sources=[EntrySource(kind="official", url="https://en.wikipedia.org/wiki/Ostra")],
    )
    objs = (
        [Proposal(proposal_id="p1", action="create", world_id=W, entry_id=None, before=None, after=draft)],
        {"p1": CheckResult(proposal_id="p1", verdict="none")},
    )
    caplog.set_level(logging.WARNING)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for obj in objs:
            assert serde.loads_typed(serde.dumps_typed(obj)) == obj
    assert "unregistered" not in caplog.text.lower(), caplog.text
