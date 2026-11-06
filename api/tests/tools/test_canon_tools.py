import json

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from sagaloom.check.contradiction import JudgeOutput
from sagaloom.models import Entry, Fact
from sagaloom.tools.canon_tools import make_tools
from sagaloom.tools.facts import FactList

W = "w1"


class StubLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0
        self.kwargs = None

    def with_structured_output(self, schema, **kwargs):
        self.kwargs = kwargs
        return self

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        return self.reply


def entry(id="ent_0001", title="Velmar", **kw):
    return Entry(id=id, world_id=W, title=title, type="place", body="A city.", **kw)


def tools_for(store, facts=None, judge=None):
    extractor = StubLLM(FactList(facts=facts if facts is not None else [Fact(key="k", value="v")]))
    judge = judge or StubLLM(JudgeOutput(flags=[]))
    ts = {t.name: t for t in make_tools(store, extractor, judge)}
    return ts, extractor, judge


def call(tool, args, id="call_1"):
    return tool.ainvoke({"type": "tool_call", "name": tool.name, "id": id, "args": args})


def msg(cmd: Command) -> ToolMessage:
    return cmd.update["messages"][0]


async def test_search_canon_wraps_results_and_includes_ids(store):
    store.upsert_entry(entry())
    ts, *_ = tools_for(store)
    out = await call(ts["search_canon"], {"query": "city", "world_id": W})
    out = out.content if hasattr(out, "content") else out
    assert out.startswith('<untrusted_data source="search_canon">')
    hits = json.loads(out.split("\n", 1)[1].rsplit("\n", 1)[0])
    assert hits["results"][0]["id"] == "ent_0001"
    assert {"title", "type", "status", "source", "snippet", "score"} <= set(hits["results"][0])


async def test_search_canon_empty_returns_reason(store):
    ts, *_ = tools_for(store)
    out = await ts["search_canon"].ainvoke({"query": "x", "world_id": W})
    assert "no matching canon in this world" in out
    assert '"results": []' in out


async def test_search_canon_is_read_only(store):
    store.upsert_entry(entry())
    ts, *_ = tools_for(store)
    for _ in range(20):
        await ts["search_canon"].ainvoke({"query": "city", "world_id": W})
    assert len(store.list_entries(W)) == 1


async def test_create_returns_proposal_and_writes_nothing(store):
    ts, *_ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "create", "title": "Ostra", "type": "place", "body": "A port.", "world_id": W, "messages": []},
        id="c9",
    )
    assert isinstance(cmd, Command)
    [p] = cmd.update["pending_proposals"]
    assert p.proposal_id.startswith("p_") and len(p.proposal_id) == 10
    assert p.action == "create" and p.after.title == "Ostra" and p.before is None
    assert p.after.facts[0].key == "k"
    m = msg(cmd)
    assert m.tool_call_id == "c9" and m.status != "error"
    assert m.content == f"Proposal {p.proposal_id} (create Ostra) is awaiting the author's review."
    assert store.list_entries(W) == []


async def test_invalid_type_returns_error_naming_field(store):
    ts, *_ = tools_for(store)
    node = ToolNode(list(ts.values()), handle_tool_errors=True)

    class S(MessagesState):
        world_id: str

    g = StateGraph(S)
    g.add_node("tools", node)
    g.add_edge(START, "tools")
    graph = g.compile()
    call_ = {
        "name": "create_or_update_entry",
        "id": "c1",
        "type": "tool_call",
        "args": {"action": "create", "title": "X", "type": "spaceship", "body": "b"},
    }
    out = await graph.ainvoke({"messages": [AIMessage(content="", tool_calls=[call_])], "world_id": W})
    m = out["messages"][-1]
    assert m.status == "error" and "type" in m.content
    assert store.list_entries(W) == []


async def test_update_requires_entry_id(store):
    ts, *_ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"], {"action": "update", "body": "new", "world_id": W, "messages": []}
    )
    assert msg(cmd).status == "error" and "entry_id" in msg(cmd).content
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_9999", "body": "n", "world_id": W, "messages": []},
    )
    assert msg(cmd).status == "error"


async def test_update_keeps_unspecified_fields_and_drafts_facts_on_body_change(store):
    old = entry(aliases=["The City"], facts=[Fact(key="a", value="b")])
    store.upsert_entry(old)
    ts, ext, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "body": "Changed.", "world_id": W, "messages": []},
    )
    [p] = cmd.update["pending_proposals"]
    assert p.before.id == "ent_0001" and p.after.title == "Velmar"
    assert p.after.aliases == ["The City"] and p.after.body == "Changed."
    assert ext.calls == 1 and p.after.facts[0].key == "k"
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "status": "myth", "world_id": W, "messages": []},
    )
    [p] = cmd.update["pending_proposals"]
    assert ext.calls == 1 and p.after.facts[0].key == "a" and p.after.status == "myth"


async def test_failed_redraft_keeps_existing_facts(store):
    store.upsert_entry(entry(facts=[Fact(key="a", value="b")]))
    ts, ext, _ = tools_for(store, facts=[])
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "body": "Changed.", "world_id": W, "messages": []},
    )
    [p] = cmd.update["pending_proposals"]
    assert ext.calls == 1 and [f.key for f in p.after.facts] == ["a"]


async def test_delete_has_no_after(store):
    store.upsert_entry(entry())
    ts, ext, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"], {"action": "delete", "entry_id": "ent_0001", "world_id": W, "messages": []}
    )
    [p] = cmd.update["pending_proposals"]
    assert p.action == "delete" and p.after is None and p.before.id == "ent_0001"
    assert ext.calls == 0
    assert len(store.list_entries(W)) == 1


async def test_create_without_facts_calls_draft_facts(store):
    ts, ext, _ = tools_for(store)
    await call(
        ts["create_or_update_entry"],
        {"action": "create", "title": "A", "type": "rule", "body": "b", "world_id": W, "messages": []},
    )
    assert ext.calls == 1
    await call(
        ts["create_or_update_entry"],
        {
            "action": "create",
            "title": "B",
            "type": "rule",
            "body": "b",
            "facts": [{"key": "x", "value": "y"}],
            "world_id": W,
            "messages": [],
        },
    )
    assert ext.calls == 1


async def test_create_with_duplicate_title_returns_error_suggesting_update(store):
    store.upsert_entry(entry(aliases=["The City"]))
    ts, *_ = tools_for(store)
    for title in ("velmar", "the city"):
        cmd = await call(
            ts["create_or_update_entry"],
            {"action": "create", "title": title, "type": "place", "body": "b", "world_id": W, "messages": []},
        )
        assert "pending_proposals" not in cmd.update
        assert msg(cmd).status == "error" and "ent_0001" in msg(cmd).content
        assert "update" in msg(cmd).content


async def test_tool_failure_returns_error_not_exception(store):
    ts, *_ = tools_for(store)

    def boom(*a, **k):
        raise RuntimeError("db down")

    store.search = boom
    store.find_by_name = boom
    out = await ts["search_canon"].ainvoke({"query": "x", "world_id": W})
    assert "error" in json.loads(out)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "create", "title": "A", "type": "rule", "body": "b", "world_id": W, "messages": []},
    )
    assert msg(cmd).status == "error"


async def test_check_contradiction_summarises_and_never_writes(store):
    store.upsert_entry(entry())
    ts, _, judge = tools_for(store)
    out = await ts["check_contradiction"].ainvoke({"proposed_text": "Velmar is a city of red rain.", "world_id": W})
    assert isinstance(out, str) and "none" in out
    assert judge.calls == 1
    assert len(store.list_entries(W)) == 1


async def test_injected_args_hidden_from_llm_schema(store):
    ts, *_ = tools_for(store)
    for t in ts.values():
        props = t.tool_call_schema.model_json_schema()["properties"]
        assert "world_id" not in props and "tool_call_id" not in props
        assert "messages" not in props
        assert not {"source", "trusted", "licence"} & set(props)
        assert t.description
    props = ts["create_or_update_entry"].tool_call_schema.model_json_schema()["properties"]
    assert props["source_url"]["description"] == "Optional: the reference URL this proposal is based on."
    assert "facts" in ts["create_or_update_entry"].description


async def test_untrusted_hit_is_labelled(store):
    store.upsert_entry(entry())
    store.upsert_entry(entry(id="ent_0002", title="Ostra", source="reference", trusted=False))
    ts, *_ = tools_for(store)
    out = await ts["search_canon"].ainvoke({"query": "city", "world_id": W})
    hits = {h["id"]: h for h in json.loads(out.split("\n", 1)[1].rsplit("\n", 1)[0])["results"]}
    assert hits["ent_0002"]["trusted"] is False
    assert hits["ent_0002"]["label"] == "untrusted source"
    assert hits["ent_0001"]["trusted"] is True
    assert "label" not in hits["ent_0001"]


async def test_messages_injection_is_required(store):
    """Called without the injected messages, the tool must fail, not fail open to user/trusted."""
    ts, *_ = tools_for(store)
    args = {"action": "create", "title": "Ostra", "type": "place", "body": "A port.", "world_id": W}
    try:
        out = await call(ts["create_or_update_entry"], args)
    except Exception:
        return
    assert not isinstance(out, Command), "a proposal was made without the turn's messages"


def test_search_hit_carries_trusted(store):
    store.upsert_entry(entry(trusted=False))
    [hit] = store.search(W, "city")
    assert hit.trusted is False


async def test_check_contradiction_failure_returns_error_not_exception(store, monkeypatch):
    ts, *_ = tools_for(store)

    async def boom(*a, **k):
        raise RuntimeError("judge down")

    monkeypatch.setattr("sagaloom.tools.canon_tools.check_proposal", boom)
    out = await ts["check_contradiction"].ainvoke({"proposed_text": "x", "world_id": W})
    assert "error" in json.loads(out)


SECRET = "buried under the quay"


def _with_secret(store):
    store.upsert_entry(
        entry(facts=[Fact(key="a", value="b"), Fact(key="Hidden", value=SECRET, status="secret")])
    )


async def test_update_omitting_a_secret_fact_keeps_it_through_commit(store):
    from sagaloom.graph.nodes import _apply

    _with_secret(store)
    ts, _, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {
            "action": "update",
            "entry_id": "ent_0001",
            "facts": [{"key": "a", "value": "changed"}],
            "world_id": W,
            "messages": [],
        },
    )
    [p] = cmd.update["pending_proposals"]
    assert {(f.key, f.value, f.status) for f in p.after.facts} == {
        ("a", "changed", "canon"),
        ("Hidden", SECRET, "secret"),
    }
    _apply(store, p)
    saved = store.get_entry(W, "ent_0001")
    assert any(f.key == "Hidden" and f.value == SECRET and f.status == "secret" for f in saved.facts)


async def test_update_result_to_the_agent_contains_no_secret_value(store):
    _with_secret(store)
    ts, _, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "facts": [{"key": "a", "value": "c"}], "world_id": W, "messages": []},
    )
    assert SECRET not in json.dumps([m.content for m in cmd.update["messages"]])


async def test_explicit_same_key_fact_replaces_the_secret(store):
    _with_secret(store)
    ts, _, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {
            "action": "update",
            "entry_id": "ent_0001",
            "facts": [{"key": "hidden", "value": "now public"}],
            "world_id": W,
            "messages": [],
        },
    )
    [p] = cmd.update["pending_proposals"]
    assert [(f.key, f.value, f.status) for f in p.after.facts] == [("hidden", "now public", "canon")]


async def test_redrafted_facts_also_keep_secrets(store):
    _with_secret(store)
    ts, _, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "body": "Changed.", "world_id": W, "messages": []},
    )
    [p] = cmd.update["pending_proposals"]
    assert any(f.status == "secret" and f.value == SECRET for f in p.after.facts)


async def test_update_keeps_every_fact_of_a_secret_entry(store):
    # A secret-status entry's facts are all hidden from the agent, whatever their own status.
    store.upsert_entry(
        entry(status="secret", facts=[Fact(key="a", value="b"), Fact(key="Hidden", value=SECRET)])
    )
    ts, _, _ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "facts": [{"key": "c", "value": "d"}], "world_id": W, "messages": []},
    )
    [p] = cmd.update["pending_proposals"]
    assert {(f.key, f.value) for f in p.after.facts} == {("c", "d"), ("a", "b"), ("Hidden", SECRET)}


async def test_check_contradiction_never_echoes_secret_flag_text(store, monkeypatch):
    from sagaloom.models import CheckResult, Flag

    _with_secret(store)
    ts, *_ = tools_for(store)

    async def judged(_store, proposal, _llm):
        return CheckResult(
            proposal_id=proposal.proposal_id,
            verdict="conflict",
            flags=[
                Flag(kind="conflict", entry_id="ent_0001", title="t", fact_key="Hidden",
                     explanation=f"Canon says it is {SECRET}.", existing_secret=True),
            ],
        )

    monkeypatch.setattr("sagaloom.tools.canon_tools.check_proposal", judged)
    out = await ts["check_contradiction"].ainvoke({"proposed_text": "x", "world_id": W})
    assert SECRET not in out
    assert "a secret fact of ent_0001 disagrees" in out


def _pending_update(pid="p_old", entry_id="ent_0001"):
    from sagaloom.models import EntryDraft, Proposal

    return Proposal(
        proposal_id=pid, action="update", world_id=W, entry_id=entry_id, before=None,
        after=EntryDraft(title="Velmar", type="place", body="Earlier wording."),
    )


async def test_update_of_an_entry_already_pending_invalidates_its_check(store):
    store.upsert_entry(entry())
    store.upsert_entry(entry(id="ent_0002", title="Ostra"))
    ts, *_ = tools_for(store)
    for action in ("update", "delete"):
        cmd = await call(
            ts["create_or_update_entry"],
            {"action": action, "entry_id": "ent_0001", "body": "Later wording.", "world_id": W,
             "messages": [], "pending": [_pending_update(), _pending_update("p_other", "ent_0002")]},
        )
        assert cmd.update["check_results"] == {"p_old": None}


async def test_proposal_for_a_new_entry_leaves_checks_alone(store):
    store.upsert_entry(entry())
    ts, *_ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "update", "entry_id": "ent_0001", "body": "Later.", "world_id": W,
         "messages": [], "pending": [_pending_update("p_other", "ent_0009")]},
    )
    assert "check_results" not in cmd.update
    assert "pending" not in ts["create_or_update_entry"].tool_call_schema.model_json_schema()["properties"]


async def test_create_never_invalidates_a_pending_check(store):
    ts, *_ = tools_for(store)
    cmd = await call(
        ts["create_or_update_entry"],
        {"action": "create", "title": "Ostra", "type": "place", "body": "A port.", "world_id": W,
         "messages": [], "pending": [_pending_update("p_new", None)]},
    )
    assert "check_results" not in cmd.update
