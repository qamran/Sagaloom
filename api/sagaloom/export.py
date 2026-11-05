"""Markdown zip export (R11.5.1, R11.5.2): one .md per entry, YAML front matter, body after it."""

import io
import re
import unicodedata
import zipfile

import yaml

from sagaloom.models import Entry


def slugify(text: str, fallback: str = "untitled", limit: int = 60) -> str:
    """Lowercase NFKD-normalised ASCII, non-alphanumerics collapsed to `-`."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:limit].strip("-") or fallback


def entry_filename(entry: Entry, taken: set[str]) -> str:
    """`<id>-<slug>.md`, made unique against `taken` (which it adds to)."""
    base = f"{entry.id}-{slugify(entry.title)}"
    name, n = f"{base}.md", 2
    while name in taken:
        name, n = f"{base}-{n}.md", n + 1
    taken.add(name)
    return name


def _render(entry: Entry) -> str:
    meta = entry.model_dump(exclude={"body"})
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    return f"---\n{front}---\n{entry.body}\n"


def export_markdown(entries: list[Entry], *, exclude_secrets: bool) -> bytes:
    """The zip bytes. `exclude_secrets` drops secret entries AND secret facts of the rest."""
    taken: set[str] = set()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in entries:
            if exclude_secrets:
                if e.status == "secret":
                    continue
                e = e.model_copy(update={"facts": [f for f in e.facts if f.status != "secret"]})
            z.writestr(entry_filename(e, taken), _render(e))
    return buf.getvalue()
