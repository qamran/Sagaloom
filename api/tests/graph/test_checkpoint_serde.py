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
        assert await run(graph, start("again"), cfg) == ["guard", "agent"]
        assert (await graph.aget_state(cfg)).values["messages"][-1].content == "two"
