"""`export_world` (R11.5): points at the Markdown zip download. Read-only; no approval."""

import json
from typing import Annotated

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

NAME = "export_world"


class ExportArgs(BaseModel):
    exclude_secrets: bool = Field(
        default=False, description="Leave out secret entries and secret facts (for sharing)."
    )
    world_id: Annotated[str, InjectedState("world_id")]


def make_export_tool(store) -> BaseTool:
    @tool(NAME, args_schema=ExportArgs)
    async def export_world(world_id: Annotated[str, InjectedState("world_id")], exclude_secrets: bool = False) -> str:
        """Export this world's canon as a Markdown zip (one file per entry, YAML front matter).
        Read-only. Returns the download path and the number of entries it will hold; tell the
        author to use that link."""
        entries = store.list_entries(world_id)
        if exclude_secrets:
            entries = [e for e in entries if e.status != "secret"]
        url = f"/api/worlds/{world_id}/export?format=md"
        if exclude_secrets:
            url += "&exclude_secrets=true"
        return json.dumps({"download": url, "entries": len(entries)})

    return export_world
