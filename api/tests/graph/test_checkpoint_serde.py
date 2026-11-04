"""R15: the runtime saver rebuilds our types without warnings, with an explicit allowlist."""

import logging
import warnings

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from sagaloom.config import Settings
from sagaloom.graph.build import run_config, sqlite_checkpointer

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
            assert p.after.title == "Ostra" and values["token_usage"].prompt_tokens == 0
            assert await only_pid(graph, cfg) == p.proposal_id
    assert not [r for r in caplog.records if "msgpack" in r.getMessage().lower() or "unregistered" in r.getMessage().lower()], caplog.text
