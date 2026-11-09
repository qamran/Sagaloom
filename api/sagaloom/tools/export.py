"""`export_world` (R11.5): points at the Markdown zip download. Read-only; no approval."""

import json
from typing import Annotated

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field

from sagaloom.store.canon import CanonStore
from sagaloom.tools.specs import EXPORT_DESCRIPTION as DESCRIPTION
from sagaloom.tools.specs import EXPORT_TOOL as NAME

# The browser reaches the API only through the Next proxy.
PROXY_PREFIX = "/api/proxy"


class ExportArgs(BaseModel):
    exclude_secrets: bool = Field(
        default=False, description="Leave out secret entries and secret facts (for sharing)."
    )
    world_id: Annotated[str, InjectedState("world_id")]


def make_export_tool(store: CanonStore) -> BaseTool:
    @tool(NAME, args_schema=ExportArgs, description=DESCRIPTION)
    async def export_world(world_id: Annotated[str, InjectedState("world_id")], exclude_secrets: bool = False) -> str:
        # Counts non-secret entries either way, so the count never reveals how many secrets exist.
        count = sum(1 for e in store.list_entries(world_id) if e.status != "secret")
        url = f"{PROXY_PREFIX}/worlds/{world_id}/export?format=md"
        if exclude_secrets:
            url += "&exclude_secrets=true"
        return json.dumps(
            {"download": url, "entries": count, "secrets_included": not exclude_secrets}
        )

    return export_world
