"""Agent tools. Write tools only PROPOSE; nothing here writes to the store (R11.2.2)."""

import json
import logging
import uuid
from typing import Annotated, Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from sagaloom.check.contradiction import check_proposal
from sagaloom.models import Entry, EntryDraft, EntryType, Fact, Proposal, SearchHit, Status
from sagaloom.provenance import merge_provenance
from sagaloom.security import wrap_untrusted
from sagaloom.store.canon import norm
from sagaloom.text import message_text
from sagaloom.tools.export import make_export_tool
from sagaloom.tools.facts import draft_facts
from sagaloom.tools.reference import NAME as REFERENCE_TOOL
from sagaloom.tools.reference import WRAP_SOURCE as REFERENCE_SOURCE
from sagaloom.tools.reference import make_reference_tool
from sagaloom.tools.specs import (  # noqa: F401  (TOOL_SPECS and CORE_TOOLS are re-exported)
    CHECK_DESCRIPTION,
    CORE_TOOLS,
    CREATE_DESCRIPTION,
    SEARCH_DESCRIPTION,
    TOOL_SPECS,
)
from sagaloom.wiki.client import WikiClient

log = logging.getLogger(__name__)

UNTRUSTED_LABEL = "untrusted source"
# How every successful real_world_reference result starts (an error result is not wrapped).
_REFERENCE_WRAP = wrap_untrusted("", REFERENCE_SOURCE).split("\n", 1)[0]

_WorldId = Annotated[str, InjectedState("world_id")]
_CallId = Annotated[str, InjectedToolCallId]
# The thread's messages, read to set provenance from the turn. Required: a call without them
# must fail rather than fall back to user/trusted.
_Messages = Annotated[list, InjectedState("messages")]


class SearchCanonArgs(BaseModel):
    query: str = Field(description="What to look for in the world's canon (names, themes, claims).")
    entry_types: list[EntryType] | None = Field(
        default=None, description="Only return these entry types."
    )
    status: Status | None = Field(default=None, description="Only return entries with this status.")
    k: int = Field(default=5, description="Number of results (max 10).")
    world_id: _WorldId


class CreateOrUpdateArgs(BaseModel):
    action: Literal["create", "update", "delete"] = Field(
        description="One of: create, update, delete."
    )
    entry_id: str | None = Field(
        default=None, description="Required for update and delete, e.g. ent_0012."
    )
    title: str | None = Field(default=None, description="Entry title (required for create).")
    type: EntryType | None = Field(default=None, description="Entry type (required for create).")
    body: str | None = Field(default=None, description="Entry prose (required for create).")
    status: Status | None = Field(
        default=None,
        description="Defaults to canon on create; kept unchanged on update.",
    )
    aliases: list[str] | None = Field(default=None, description="Alternative names.")
    facts: list[Fact] | None = Field(
        default=None, description=(
            "Key/value facts. Omit to have them drafted from the body. On update this REPLACES the "
            "whole list: pass every existing fact, keep existing keys exactly as they are, and "
            "change only the values the author changed."
        )
    )
    source_url: str | None = Field(
        default=None, description="Optional: the reference URL this proposal is based on."
    )
    world_id: _WorldId
    tool_call_id: _CallId
    messages: _Messages


class CheckContradictionArgs(BaseModel):
    proposed_text: str = Field(description="A hypothetical claim or passage to check against canon.")
    world_id: _WorldId


def _err(call_id: str, text: str) -> Command:
    return Command(
        update={"messages": [ToolMessage(content=text, tool_call_id=call_id, status="error")]}
    )


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _bad_fields(e: ValidationError) -> str:
    bad = sorted({str(x["loc"][0]) for x in e.errors() if x["loc"]})
    return f"Invalid fields: {', '.join(bad)}. {e.errors()[0]['msg']}"


def _hit(h: SearchHit) -> dict[str, Any]:
    """An untrusted entry is labelled as such when retrieved (R13.7)."""
    d = h.model_dump()
    if not h.trusted:
        d["label"] = UNTRUSTED_LABEL
    return d


def _keep_secret_facts(before: Entry, proposed: list[Fact]) -> list[Fact]:
    """The agent never sees secret facts (nor any fact of a secret entry), so an update that
    omits one cannot mean to delete it: carry over every such fact whose key the proposal does
    not mention. A proposed fact with the same key replaces it."""
    keys = {norm(f.key) for f in proposed}
    hidden = before.status == "secret"
    kept = [f for f in before.facts if (hidden or f.status == "secret") and norm(f.key) not in keys]
    return [*proposed, *kept]


def _reference_turn(messages: list | None) -> tuple[bool, list[str]]:
    """(whether `real_world_reference` returned a successful reference payload in this turn, the
    URLs it returned). The turn is everything after the author's last message (an unnamed
    HumanMessage; review notes are named). An error result, a validation error or an unparseable
    message brings no reference text in, so it does not count."""
    turn: list = []
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage) and not m.name:
            break
        turn.append(m)
    called = False
    urls: list[str] = []
    for m in reversed(turn):
        if not (isinstance(m, ToolMessage) and m.name == REFERENCE_TOOL):
            continue
        if m.status == "error":
            continue
        text = message_text(m.content)
        if not text.startswith(_REFERENCE_WRAP):
            continue  # the soft error result is plain JSON, never wrapped
        try:  # the payload sits between the wrapper's first and last line
            payload = json.loads(text.split("\n", 1)[1].rsplit("\n", 1)[0])
        except (IndexError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("label") != "reference":
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        called = True
        for r in results:
            url = r.get("url") if isinstance(r, dict) else None
            if isinstance(url, str) and url not in urls:
                urls.append(url)
    return called, urls


def reference_urls_this_turn(messages: list) -> list[str]:
    """The URLs `real_world_reference` returned in this turn; empty if it was not called."""
    return _reference_turn(messages)[1]


def _provenance(messages: list | None, source_url: str | None) -> dict[str, Any]:
    """Server-set provenance for a chat proposal (R11.4.6). A successful `real_world_reference`
    payload in this turn taints it. The agent may pick which of the turn's URLs it used; anything
    else it names is ignored, and the first of the turn's URLs is stored instead."""
    called, urls = _reference_turn(messages)
    if not called:
        return {"source": "user", "source_url": None, "licence": None, "trusted": True}
    url = source_url if source_url in urls else (urls[0] if urls else None)
    return {"source": "reference", "source_url": url, "licence": None, "trusted": False}


def make_tools(
    store,
    extractor_llm: BaseChatModel,
    judge_llm: BaseChatModel,
    wiki: WikiClient | None = None,
) -> list[BaseTool]:
    @tool("search_canon", args_schema=SearchCanonArgs, description=SEARCH_DESCRIPTION)
    async def search_canon(
        query: str,
        world_id: _WorldId,
        entry_types: list[str] | None = None,
        status: str | None = None,
        k: int = 5,
    ) -> str:
        try:
            hits = store.search(
                world_id, query, k=k, entry_types=entry_types, statuses=[status] if status else None
            )
            if not hits:
                payload = {"results": [], "reason": "no matching canon in this world"}
            else:
                payload = {"results": [_hit(h) for h in hits]}
            return wrap_untrusted(_json(payload), "search_canon")
        except Exception as e:
            log.warning("search_canon failed", exc_info=True)
            return _json({"error": f"search failed: {e}"})

    @tool("create_or_update_entry", args_schema=CreateOrUpdateArgs, description=CREATE_DESCRIPTION)
    async def create_or_update_entry(
        action: Literal["create", "update", "delete"],
        world_id: _WorldId,
        tool_call_id: _CallId,
        messages: _Messages,
        entry_id: str | None = None,
        title: str | None = None,
        type: EntryType | None = None,
        body: str | None = None,
        status: Status | None = None,
        aliases: list[str] | None = None,
        facts: list[Fact] | None = None,
        source_url: str | None = None,
    ) -> Command:
        try:
            prov = _provenance(messages, source_url)
            before = None
            after = None
            if action in ("update", "delete"):
                if not entry_id:
                    return _err(tool_call_id, f"Field 'entry_id' is required for {action}.")
                before = store.get_entry(world_id, entry_id)
                if before is None:
                    return _err(tool_call_id, f"No entry '{entry_id}' in this world. Search first.")

            if action == "create":
                if body is None:
                    return _err(tool_call_id, "Invalid fields: body. It is required for create.")
                if existing := store.find_by_name(world_id, title or ""):
                    return _err(
                        tool_call_id,
                        f"An entry named '{existing.title}' already exists ({existing.id}). "
                        f"Propose an update with entry_id='{existing.id}' instead.",
                    )
                try:
                    after = EntryDraft(
                        title=title or "",
                        type=type,
                        body=body,
                        status=status or "canon",
                        aliases=aliases or [],
                        facts=facts or [],
                        **prov,
                    )
                except ValidationError as e:
                    return _err(tool_call_id, _bad_fields(e))
                if facts is None:
                    after.facts = await draft_facts(after.title, after.body, extractor_llm)
            elif action == "update":
                try:
                    after = EntryDraft(
                        title=title if title is not None else before.title,
                        type=type if type is not None else before.type,
                        body=body if body is not None else before.body,
                        status=status if status is not None else before.status,
                        aliases=aliases if aliases is not None else before.aliases,
                        facts=facts if facts is not None else before.facts,
                        # Pre-merged with the stored entry so the card shows what will be
                        # stored; the commit merges again as the guard.
                        **merge_provenance(before, EntryDraft.model_construct(**prov)),
                    )
                except ValidationError as e:
                    return _err(tool_call_id, _bad_fields(e))
                if facts is None and body is not None and body != before.body:
                    after.facts = (
                        await draft_facts(after.title, after.body, extractor_llm) or before.facts
                    )
                after.facts = _keep_secret_facts(before, after.facts)

            proposal = Proposal(
                proposal_id="p_" + uuid.uuid4().hex[:8],
                action=action,
                world_id=world_id,
                entry_id=entry_id,
                before=before,
                after=after,
            )
            label = after.title if after else before.title
            text = f"Proposal {proposal.proposal_id} ({action} {label}) is awaiting the author's review."
            return Command(
                update={
                    "pending_proposals": [proposal],
                    "messages": [ToolMessage(content=text, tool_call_id=tool_call_id)],
                }
            )
        except Exception as e:
            log.warning("create_or_update_entry failed", exc_info=True)
            return _err(tool_call_id, f"Could not prepare the proposal: {e}")

    @tool("check_contradiction", args_schema=CheckContradictionArgs, description=CHECK_DESCRIPTION)
    async def check_contradiction(proposed_text: str, world_id: _WorldId) -> str:
        try:
            facts = await draft_facts("(hypothetical)", proposed_text, extractor_llm)
            proposal = Proposal(
                proposal_id="p_" + uuid.uuid4().hex[:8],
                action="create",
                world_id=world_id,
                entry_id=None,
                before=None,
                after=EntryDraft(
                    title="(hypothetical)", type="rule", body=proposed_text[:4000], facts=facts
                ),
            )
            result = await check_proposal(store, proposal, judge_llm)
            lines = [f"verdict: {result.verdict}"]
            for f in result.flags:
                # Never echo a secret back to the agent: the judge's text may quote it.
                why = (
                    f"a secret fact of {f.entry_id} disagrees"
                    if f.existing_secret
                    else f.explanation
                )
                lines.append(f"- {f.kind} {f.entry_id} fact_key={f.fact_key}: {why}")
            return "\n".join(lines)
        except Exception as e:
            log.warning("check_contradiction failed", exc_info=True)
            return _json({"error": f"contradiction check failed: {e}"})

    tools: list[BaseTool] = [search_canon, create_or_update_entry, check_contradiction]
    tools.append(make_export_tool(store))
    if wiki is not None:
        tools.append(make_reference_tool(wiki))
    return tools
