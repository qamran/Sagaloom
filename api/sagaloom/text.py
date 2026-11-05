"""Neutral helpers shared by the graph and web layers."""

from typing import Any


def message_text(content: Any) -> str:
    """Plain text of a message's content: a string, or the text blocks of a content list.
    Anything else is empty."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else (b if isinstance(b, str) else "")
            for b in content
        )
    return ""
