"""Agent tools. Write tools only PROPOSE; nothing here writes to the store (R11.2.2)."""

import json
import logging
import uuid
from typing import Annotated, Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from sagaloom.check.contradiction import check_proposal
from sagaloom.models import EntryDraft, EntryType, Fact, Proposal, Status
from sagaloom.security import wrap_untrusted
from sagaloom.tools.facts import draft_facts

log = logging.getLogger(__name__)

_WorldId = Annotated[str, InjectedState("world_id")]
_CallId = Annotated[str, InjectedToolCallId]


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
    world_id: _WorldId
    tool_call_id: _CallId


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


def make_tools(store, extractor_llm: BaseChatModel, judge_llm: BaseChatModel) -> list[BaseTool]:
    @tool("search_canon", args_schema=SearchCanonArgs)
    async def search_canon(
        query: str,
        world_id: _WorldId,
        entry_types: list[str] | None = None,
        status: str | None = None,
        k: int = 5,
    ) -> str:
        """Search this world's canon by meaning. Read-only. Returns matching entries (id, title,
        type, status, source, snippet, score) as untrusted data; cite entry ids when you use them."""
        try:
            hits = store.search(
                world_id, query, k=k, entry_types=entry_types, statuses=[status] if status else None
            )
            if not hits:
                payload = {"results": [], "reason": "no matching canon in this world"}
            else:
                payload = {"results": [h.model_dump() for h in hits]}
            return wrap_untrusted(_json(payload), "search_canon")
        except Exception as e:
            log.warning("search_canon failed", exc_info=True)
            return _json({"error": f"search failed: {e}"})

    @tool("create_or_update_entry", args_schema=CreateOrUpdateArgs)
    async def create_or_update_entry(
        action: Literal["create", "update", "delete"],
        world_id: _WorldId,
        tool_call_id: _CallId,
        entry_id: str | None = None,
        title: str | None = None,
        type: EntryType | None = None,
        body: str | None = None,
        status: Status | None = None,
        aliases: list[str] | None = None,
        facts: list[Fact] | None = None,
    ) -> Command:
        """Propose creating, updating or deleting a canon entry. This does NOT change canon: it
        queues a proposal that is contradiction-checked and shown to the author for approval."""
        try:
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
                    )
                except ValidationError as e:
                    return _err(tool_call_id, _bad_fields(e))
                if facts is None and body is not None and body != before.body:
                    after.facts = (
                        await draft_facts(after.title, after.body, extractor_llm) or before.facts
                    )

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

    @tool("check_contradiction", args_schema=CheckContradictionArgs)
    async def check_contradiction(proposed_text: str, world_id: _WorldId) -> str:
        """Check a hypothetical claim against this world's canon without proposing anything.
        Read-only. Returns a verdict (none, possible, conflict, failed) and any flags."""
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
                lines.append(f"- {f.kind} {f.entry_id} fact_key={f.fact_key}: {f.explanation}")
            return "\n".join(lines)
        except Exception as e:
            log.warning("check_contradiction failed", exc_info=True)
            return _json({"error": f"contradiction check failed: {e}"})

    return [search_canon, create_or_update_entry, check_contradiction]
