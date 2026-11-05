"""Long-term author preferences (R10.2, spec §3.5).

A small typed set per world, kept in a LangGraph Store under `("preferences", world_id)`, one
item per key with value `{"value": str | list[str]}`. Only the graph's `remember` node calls
`apply_updates`; tools never write.

The injection defence is the **verbatim gate**: a value is stored only if the author said it,
near-verbatim, in the latest message they typed. A preference planted in a retrieved entry, a
reference summary or imported text never appears there, so it can never reach the Store and
from there every later system prompt.
"""

import re

from langgraph.store.base import BaseStore

from sagaloom.models import MemoryResult, MemoryUpdate, PreferenceKey

__all__ = [
    "CAP",
    "KEY_ORDER",
    "LIST_KEYS",
    "PreferenceKey",
    "apply_updates",
    "forget",
    "namespace",
    "near_verbatim",
    "read_preferences",
    "render_preferences",
]

KEY_ORDER: tuple[str, ...] = ("tone", "genre", "banned_tropes", "notes")
LIST_KEYS = frozenset({"banned_tropes", "notes"})
CAP = 20  # items per world: a set string key counts 1, a list counts its length
MAX_CHARS = 200
HEADING = "Author preferences (stated by the author in chat):"

_TOKEN_SPLIT = re.compile(r"\W+")


def namespace(world_id: str) -> tuple[str, str]:
    return ("preferences", world_id)


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN_SPLIT.split(s.lower()) if t}


def near_verbatim(value: str, message: str) -> bool:
    """True if `value` is something the author said in `message`: a case- and
    whitespace-normalised substring, or (for 2 to 5 tokens) at least 80% of its tokens appear in
    the message. A one-token value passes only as a substring."""
    v = norm(value)
    if not v:
        return False
    if v in norm(message):
        return True
    vt = _tokens(value)
    if not 2 <= len(vt) < 6:
        return False
    return len(vt & _tokens(message)) / len(vt) >= 0.8


async def read_preferences(store: BaseStore, world_id: str) -> dict[str, str | list[str]]:
    """The preferences that are set, in key order."""
    out: dict[str, str | list[str]] = {}
    for key in KEY_ORDER:
        item = await store.aget(namespace(world_id), key)
        value = (item.value or {}).get("value") if item is not None else None
        if key in LIST_KEYS:
            if isinstance(value, list) and value:
                out[key] = [str(v) for v in value]
        elif isinstance(value, str) and value:
            out[key] = value
    return out


def count_items(prefs: dict[str, str | list[str]]) -> int:
    return sum(len(v) if isinstance(v, list) else 1 for v in prefs.values())


def _stored(key: str, value: str) -> str:
    return f"Remembered: {key} → {value}"


def _gated(key: str, value: str) -> str:
    return f"Not remembered: it wasn't something the author said ({key}: {value})"


def _full(key: str, value: str) -> str:
    return f"Not remembered: memory is full ({CAP} preferences) ({key}: {value})"


def _invalid(key: str) -> str:
    return f"Not remembered: preferences must be one line of at most {MAX_CHARS} characters ({key})"


async def apply_updates(
    store: BaseStore, world_id: str, updates: list[MemoryUpdate], author_text: str
) -> list[MemoryResult]:
    """Gate and write each update in order; one result per update. Checks, in order: one line
    of 1-200 characters, the verbatim gate against `author_text`, then the cap."""
    prefs = await read_preferences(store, world_id)
    results: list[MemoryResult] = []
    for u in updates:
        key, raw = u.key, u.value
        value = raw.strip()
        if "\n" in raw or "\r" in raw or not 1 <= len(value) <= MAX_CHARS:
            # Bounded, since the result is kept in the thread and streamed to the client.
            results.append(
                MemoryResult(key=key, value=value[:MAX_CHARS], stored=False, note=_invalid(key))
            )
            continue
        if not near_verbatim(value, author_text):
            results.append(
                MemoryResult(key=key, value=value, stored=False, note=_gated(key, value))
            )
            continue
        if key in LIST_KEYS:
            items = list(prefs.get(key) or [])
            if any(norm(i) == norm(value) for i in items):  # already there: not added twice
                results.append(
                    MemoryResult(key=key, value=value, stored=True, note=_stored(key, value))
                )
                continue
            if count_items(prefs) >= CAP:
                results.append(
                    MemoryResult(key=key, value=value, stored=False, note=_full(key, value))
                )
                continue
            new: str | list[str] = [*items, value]
        else:
            if key not in prefs and count_items(prefs) >= CAP:
                results.append(
                    MemoryResult(key=key, value=value, stored=False, note=_full(key, value))
                )
                continue
            new = value
        await store.aput(namespace(world_id), key, {"value": new})
        prefs[key] = new
        results.append(MemoryResult(key=key, value=value, stored=True, note=_stored(key, value)))
    return results


async def forget(
    store: BaseStore, world_id: str, key: PreferenceKey, item: str | None = None
) -> dict[str, str | list[str]]:
    """Remove a key, or one list item (matched after `norm`). For a string key, `item` (if
    given) must match the current value, so a stale Undo never removes a newer value. Removing
    something that isn't set is not an error. Returns the preferences left."""
    prefs = await read_preferences(store, world_id)
    current = prefs.get(key)
    if current is not None:
        if item is None:
            await store.adelete(namespace(world_id), key)
        elif isinstance(current, list):
            left = [i for i in current if norm(i) != norm(item)]
            if not left:
                await store.adelete(namespace(world_id), key)
            elif len(left) != len(current):
                await store.aput(namespace(world_id), key, {"value": left})
        elif norm(current) == norm(item):
            await store.adelete(namespace(world_id), key)
    return await read_preferences(store, world_id)


def render_preferences(prefs: dict) -> str:
    """The system-prompt block: one bullet per string key and per list item, in key order.
    Empty when nothing is stored."""
    lines: list[str] = []
    for key in KEY_ORDER:
        value = prefs.get(key)
        if isinstance(value, list):
            lines += [f"- {key}: {v}" for v in value]
        elif value:
            lines.append(f"- {key}: {value}")
    return "\n".join([HEADING, *lines]) if lines else ""
