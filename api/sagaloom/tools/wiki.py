"""`import_wiki` (R-W3-6, R11.6): fan-wiki pages as proposals for the author's review.

It writes nothing: the plan's proposals go to `pending_proposals`, so `check` and `approval_gate`
see them before `commit` can write. The agent never sees page text: the result holds counts,
page titles and not-imported reasons only, and is itself wrapped as untrusted data.
"""

import json
import logging
from typing import TYPE_CHECKING, Annotated

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field

from sagaloom.importing.extract import EXTRACTION_FAILED
from sagaloom.importing.wiki import LICENCE_UNREADABLE, build_wiki_import, fetch_wiki
from sagaloom.security import wrap_untrusted
from sagaloom.tools.specs import IMPORT_WIKI_DESCRIPTION as DESCRIPTION
from sagaloom.tools.specs import IMPORT_WIKI_TOOL as NAME
from sagaloom.wiki.client import LicenceUnreadable, WikiClient
from sagaloom.wiki.pages import MAX_URLS, BadWikiUrl, parse_page_urls

if TYPE_CHECKING:
    from sagaloom.structured import ChatModelLike

log = logging.getLogger(__name__)

_WorldId = Annotated[str, InjectedState("world_id")]
_CallId = Annotated[str, InjectedToolCallId]

AWAITING = "The proposals are awaiting the author's review in the chat card; canon is unchanged until they approve."
NOTHING_PROPOSED = "Nothing was proposed, so canon is unchanged."


class ImportWikiArgs(BaseModel):
    urls: list[str] = Field(
        min_length=1,
        max_length=MAX_URLS,
        description="1-10 page URLs from one wiki, exactly as the author gave them "
        "(e.g. https://en.wikipedia.org/wiki/Gandalf).",
    )
    world_id: _WorldId
    tool_call_id: _CallId


def _err(call_id: str, text: str) -> Command:
    return Command(
        update={"messages": [ToolMessage(content=text, tool_call_id=call_id, name=NAME, status="error")]}
    )


def make_import_wiki_tool(store, client: WikiClient, extractor_llm: "ChatModelLike") -> BaseTool:
    @tool(NAME, args_schema=ImportWikiArgs, description=DESCRIPTION)
    async def import_wiki(
        urls: list[str], world_id: _WorldId, tool_call_id: _CallId, config: RunnableConfig
    ) -> Command:
        try:
            pages = parse_page_urls(urls)
            fetched = await fetch_wiki(client, pages)
            # The turn's config, so the extractor's prompt records log under this turn.
            plan = await build_wiki_import(store, extractor_llm, world_id, fetched, config=config)
        except BadWikiUrl as e:
            return _err(tool_call_id, str(e))
        except LicenceUnreadable as e:
            return _err(tool_call_id, LICENCE_UNREADABLE.format(host=e.host))
        except Exception as e:
            # The type only: an exception's message may quote page text (R-W3-6).
            log.warning("import_wiki failed", exc_info=True)
            return _err(tool_call_id, f"Could not import those pages: {type(e).__name__}")
        if plan.extraction_failed:
            return _err(tool_call_id, plan.failure or EXTRACTION_FAILED)
        result = {
            "label": NAME,
            "proposals": len(plan.proposals),
            # Titles only: never an excerpt, body, fact or wikitext.
            "pages": [
                {"title": p.after.title if p.after else p.before.title, "action": p.action}
                for p in plan.proposals
            ],
            "not_imported": [{"title": s.title, "reason": s.reason} for s in plan.skipped],
            "licence": fetched.licence.display,
            "nc": fetched.licence.nc,
            "note": AWAITING if plan.proposals else NOTHING_PROPOSED,
        }
        content = wrap_untrusted(json.dumps(result, ensure_ascii=False), NAME)
        return Command(
            update={
                "pending_proposals": plan.proposals,
                "messages": [ToolMessage(content=content, tool_call_id=tool_call_id, name=NAME)],
            }
        )

    return import_wiki
