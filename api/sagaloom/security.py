import re

_CLOSE_TAG = re.compile(r"</(untrusted_data)", re.IGNORECASE)


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def wrap_untrusted(text: str, source: str) -> str:
    """Wrap text as data so an LLM treats it as content, never as instructions (R13.2)."""
    safe = _CLOSE_TAG.sub(lambda m: "&lt;/" + m.group(1), text)
    return f'<untrusted_data source="{_escape_attr(source)}">\n{safe}\n</untrusted_data>'
