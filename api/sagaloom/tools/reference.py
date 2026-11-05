"""`real_world_reference` (R11.4): Wikipedia as inspiration, never as canon. Read-only."""

import json
import logging

import httpx
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from sagaloom.security import wrap_untrusted
from sagaloom.wiki.client import WikiClient, search_and_summarise

log = logging.getLogger(__name__)

DESCRIPTION = """Look up real-world history, places or things on Wikipedia for inspiration. Read-only.
Returns article titles, short summaries and URLs labelled as reference: they are NOT part
of the world's canon."""
NAME = "real_world_reference"
WRAP_SOURCE = "real_world_reference (reference, not canon)"


class ReferenceArgs(BaseModel):
    query: str = Field(
        min_length=1, max_length=200, description="What to look up on Wikipedia (a real-world topic)."
    )
    max_results: int = Field(default=3, ge=1, le=5, description="Number of articles (1-5).")


def _reason(e: Exception) -> str:
    if isinstance(e, httpx.TimeoutException):
        return "the request timed out"
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    if isinstance(e, httpx.HTTPError):
        return "network error"
    if isinstance(e, ValueError):
        return "unexpected response"
    return type(e).__name__


def make_reference_tool(client: WikiClient) -> BaseTool:
    @tool(NAME, args_schema=ReferenceArgs, description=DESCRIPTION)
    async def real_world_reference(query: str, max_results: int = 3) -> str:
        try:
            results = await search_and_summarise(client, query, max_results)
        except Exception as e:  # R11.4.7: the agent carries on without it
            log.warning("real_world_reference failed: %s", type(e).__name__, exc_info=True)
            return json.dumps({"error": f"Wikipedia lookup unavailable: {_reason(e)}"})
        payload = {"label": "reference", "results": [r.model_dump() for r in results]}
        return wrap_untrusted(json.dumps(payload, ensure_ascii=False), WRAP_SOURCE)

    return real_world_reference
