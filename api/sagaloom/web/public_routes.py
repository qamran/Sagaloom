"""Routes for logged-out visitors (M5 spec §5.7). Behind the shared secret like every /api
route, but with no signed-in user; they serve frozen data and never call a model."""

import json
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

PREVIEW_FILE = Path(__file__).resolve().parents[1] / "public" / "preview.json"

router = APIRouter()


@cache
def _preview() -> dict[str, Any]:
    """Read once: the file is part of the release, made by `scripts/make_preview_fixture.py`."""
    return json.loads(PREVIEW_FILE.read_text(encoding="utf-8"))


@router.get("/public/preview")
def get_preview() -> dict[str, Any]:
    """The home page's Velmar example: the chat, its approval card and a few entries, in the
    shapes of `GET /threads/{id}` and `GET /worlds/{id}/entries`."""
    return _preview()
