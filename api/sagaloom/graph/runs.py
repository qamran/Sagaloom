"""Which graph nodes the newest run went through, for the Studio's highlighted graph."""

from typing import Any


async def last_run_nodes(graph: Any, thread_id: str) -> dict:
    """{"nodes": [...], "paused": bool} for the thread's newest run.

    Walks the checkpoint history newest first and collects the names of the tasks that ran from
    each snapshot, until the newest snapshot created by a new input. LangGraph 1.2 metadata has
    no `writes`, so task names are the record. The newest snapshot's pending tasks count too, so
    a waiting approval gate shows. A decision resume makes no input snapshot, so its run reaches
    back to the turn's message (deliberate)."""
    config = {"configurable": {"thread_id": thread_id}}
    newest_first: list[str] = []
    paused = False
    first = True
    async for snap in graph.aget_state_history(config):
        if first:
            paused = bool(snap.interrupts)
        for task in snap.tasks:
            if first or task.result is not None:
                newest_first.append(task.name)
        first = False
        if (snap.metadata or {}).get("source") == "input":
            break
    nodes: list[str] = []
    for name in reversed(newest_first):
        if name != "__start__" and name not in nodes:
            nodes.append(name)
    return {"nodes": nodes, "paused": paused}
