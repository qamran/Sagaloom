"""Licence checks for imported content (R-W3). No project imports, so `models` can use it."""

import re

_NC_TEXT = re.compile(r"\bNC\b")
_NC_WORD = re.compile(r"non-?commercial", re.IGNORECASE)
_NC_URL = re.compile(r"/by-nc|-nc[-/]", re.IGNORECASE)


def is_nc(text: str | None, url: str | None) -> bool:
    """True when the licence text or its URL marks the content non-commercial (CC `NC`)."""
    if text and (_NC_TEXT.search(text) or _NC_WORD.search(text)):
        return True
    return bool(url and _NC_URL.search(url))
