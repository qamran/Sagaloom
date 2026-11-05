"""last_run_nodes: the nodes the newest run went through (Wave 3 task 4)."""

from langchain_core.messages import AIMessage

from sagaloom.graph.build import run_config
from sagaloom.graph.runs import last_run_nodes

from test_graph import W, create_call, make, only_pid, resume, run, start


async def test_last_run_plain_answer(store):
    graph, *_ = make(store, [AIMessage(content="Velmar has one moon.")])
    cfg = run_config("t1", W)
    await run(graph, start("How many moons?"), cfg)
    assert await last_run_nodes(graph, "t1") == {
        "nodes": ["guard", "router", "agent"],
        "paused": False,
    }


async def test_last_run_paused_at_gate(store):
    graph, *_ = make(store, [create_call()])
    cfg = run_config("t1", W)
    await run(graph, start(), cfg)
    out = await last_run_nodes(graph, "t1")
    assert out["paused"] is True
    assert out["nodes"][:3] == ["guard", "router", "agent"]
    for n in ("tools", "check", "approval_gate"):
        assert n in out["nodes"]
    assert "commit" not in out["nodes"]


async def test_last_run_after_decision_resume_spans_the_turn(store):
    graph, *_ = make(store, [create_call(), AIMessage(content="Saved.")])
    cfg = run_config("t1", W)
    await run(graph, start(), cfg)
    pid = await only_pid(graph, cfg)
    await run(graph, resume({"proposal_id": pid, "action": "approve"}), cfg)
    out = await last_run_nodes(graph, "t1")
    assert out["paused"] is False
    assert out["nodes"][0] == "guard" and "commit" in out["nodes"]
    assert len(out["nodes"]) == len(set(out["nodes"]))


async def test_last_run_no_checkpoints(store):
    graph, *_ = make(store, [])
    assert await last_run_nodes(graph, "nothing") == {"nodes": [], "paused": False}
