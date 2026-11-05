"""`remember_preference` (R10.2, spec §3.5): queues an author preference. It writes nothing:
the `remember` node gates the value against the author's own message and writes the Store."""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from sagaloom.memory import MAX_CHARS
from sagaloom.models import MemoryUpdate, PreferenceKey
from sagaloom.tools.specs import MEMORY_DESCRIPTION as DESCRIPTION
from sagaloom.tools.specs import MEMORY_TOOL as NAME

_CallId = Annotated[str, InjectedToolCallId]


class RememberArgs(BaseModel):
    key: PreferenceKey = Field(
        description="tone or genre (one value each), banned_tropes or notes (one item per call)."
    )
    value: str = Field(description="The author's exact words, copied from their message.")
    tool_call_id: _CallId


def make_memory_tool() -> BaseTool:
    @tool(NAME, args_schema=RememberArgs, description=DESCRIPTION)
    async def remember_preference(key: PreferenceKey, value: str, tool_call_id: _CallId) -> Command:
        # The ToolMessage answers this call id; without it the next agent call would carry a
        # dangling tool_call.
        text = f"Queued: {key} → {value[:MAX_CHARS]}. It is stored only if the author said it."
        return Command(
            update={
                "memory_updates": [MemoryUpdate(key=key, value=value)],
                "messages": [ToolMessage(content=text, tool_call_id=tool_call_id, name=NAME)],
            }
        )

    return remember_preference
