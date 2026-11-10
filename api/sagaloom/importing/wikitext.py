"""Plain text from MediaWiki wikitext (M3 design §5.4).

A hand-written stripper, not `mwparserfromhell`: the rules are a short, fixed list, the output
must be byte-stable because `locate` searches it, and a new dependency would buy parse-tree
features nothing here uses. The first `{{Infobox …}}` is captured before templates are dropped;
its non-empty values lead the text as `Key: Value` lines.
"""

import html
import re

from pydantic import BaseModel

from sagaloom.models import EntryType

_HEADING_MARK = "\x00"  # replaces a heading line's start while whitespace is normalised

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SELF_CLOSED_REF = re.compile(r"<ref\b[^>]*/>", re.IGNORECASE)
_BLOCK_TAGS = [
    re.compile(rf"<{tag}\b[^>]*>.*?</{tag}\s*>", re.IGNORECASE | re.DOTALL)
    for tag in ("ref", "gallery", "math")
]
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_LINK = re.compile(r"\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]")
_DROPPED_NAMESPACES = ("file:", "image:", "category:")
_EXTERNAL = re.compile(
    r"\[(?:(?:https?|ftps?|sftp|news|irc|ircs|gopher)://|//|mailto:)[^\s\]]+(?:[ \t]+([^\]]*))?\]",
    re.IGNORECASE,
)
_MAGIC_WORD = re.compile(r"__[A-Z]+__")
_QUOTES = re.compile(r"'{2,}")
_HEADING = re.compile(r"^(={1,6})[ \t]*(.*?)[ \t]*\1[ \t]*$")
_LIST_MARKER = re.compile(r"^[*#:;]+[ \t]*")
_SPACES = re.compile(r"[ \t]+")
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r" +([.,;:])")


class StrippedPage(BaseModel):
    text: str  # the infobox lines, then the article prose
    infobox_name: str | None
    infobox: dict[str, str]  # parameter name as written -> stripped value, in order
    lead_end: int  # where the first heading's line starts in `text`, or len(text)


def _find_close(text: str, start: int, opener: str, closer: str) -> int:
    """The index just past the `closer` matching the `opener` at `start`, or -1."""
    depth, i = 0, start
    while i < len(text):
        if text.startswith(opener, i):
            depth += 1
            i += len(opener)
        elif text.startswith(closer, i):
            depth -= 1
            i += len(closer)
            if depth == 0:
                return i
        else:
            i += 1
    return -1


def _remove_tables(text: str) -> str:
    """Drop each `{|` ... `|}` table; one that never closes loses only its opener line."""
    lines = text.split("\n")
    drop: set[int] = set()
    for first, line in enumerate(lines):
        if first in drop or not line.lstrip().startswith("{|"):
            continue
        depth = 0
        for i in range(first, len(lines)):
            head = lines[i].strip()
            depth += head.startswith("{|")
            depth -= head.endswith("|}")
            if depth <= 0:
                drop.update(range(first, i + 1))
                break
        else:
            drop.add(first)
    return "\n".join(line for i, line in enumerate(lines) if i not in drop)


def _split_params(body: str) -> list[str]:
    """Split a template body on its top-level `|`s (not those inside nested `{{ }}` or `[[ ]]`)."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            i += 2
        elif pair in ("}}", "]]"):
            depth = max(depth - 1, 0)
            i += 2
        else:
            if body[i] == "|" and depth == 0:
                parts.append(body[start:i])
                start = i + 1
            i += 1
    parts.append(body[start:])
    return parts


def _remove_templates(text: str) -> tuple[str, str | None, dict[str, str]]:
    """Drop every `{{…}}`; return the text and the first Infobox template, parsed."""
    out, i = [], 0
    infobox_name: str | None = None
    infobox: dict[str, str] = {}
    while True:
        start = text.find("{{", i)
        if start == -1:
            out.append(text[i:])
            break
        end = _find_close(text, start, "{{", "}}")
        out.append(text[i:start])
        if end == -1:  # unbalanced: drop just the opener
            i = start + 2
            continue
        if infobox_name is None:
            name, *params = _split_params(text[start + 2 : end - 2])
            if name.strip().casefold().startswith("infobox"):
                infobox_name = " ".join(name.split())
                for param in params:
                    key, eq, value = param.partition("=")
                    if eq and key.strip():
                        infobox[key.strip()] = _inline(value)
        i = end
    return "".join(out), infobox_name, infobox


def _remove_file_links(text: str) -> str:
    out, i = [], 0
    while True:
        start = text.find("[[", i)
        if start == -1:
            out.append(text[i:])
            break
        out.append(text[i:start])
        if not text[start + 2 :].lstrip().casefold().startswith(_DROPPED_NAMESPACES):
            out.append("[[")
            i = start + 2
            continue
        end = _find_close(text, start, "[[", "]]")
        i = start + 2 if end == -1 else end
    return "".join(out)


def _replace_links(text: str) -> str:
    def shown(m: re.Match) -> str:
        return m.group(2) if m.group(2) is not None else m.group(1)

    while True:  # innermost first: a link in another link's label resolves before the outer one
        replaced = _LINK.sub(shown, text)
        if replaced == text:
            return text
        text = replaced


def _clean(text: str) -> str:
    """Everything except templates, tables, headings and lists, which `strip_wikitext` handles."""
    text = _remove_file_links(text)
    text = _replace_links(text)
    text = _EXTERNAL.sub(lambda m: m.group(1) or "", text)
    text = _MAGIC_WORD.sub("", text)
    text = _BR.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    return _QUOTES.sub("", text)  # after unescaping, so `&#39;&#39;` runs go too


def _tidy(line: str) -> str:
    """What template and ref removal leaves behind: empty `()`, runs of spaces, a space before
    `.` `,` `;` `:`. Repeated until stable, so stripping the result again changes nothing."""
    while True:
        tidy = _SPACES.sub(" ", _EMPTY_PARENS.sub("", line))
        tidy = _SPACE_BEFORE_PUNCT.sub(r"\1", tidy).strip()
        if tidy == line:
            return tidy
        line = tidy


def _remove_blocks(text: str) -> str:
    text = _COMMENT.sub("", text)
    text = _SELF_CLOSED_REF.sub("", text)
    for pattern in _BLOCK_TAGS:
        text = pattern.sub("", text)
    return text


def _inline(value: str) -> str:
    """An infobox value as one line of plain text."""
    value, _, _ = _remove_templates(_remove_blocks(value))
    parts = (_tidy(_LIST_MARKER.sub("", p.strip())) for p in _clean(value).split("\n"))
    return ", ".join(part for part in parts if part)


def _key_label(key: str) -> str:
    return key.replace("_", " ").title()


def strip_wikitext(wikitext: str) -> StrippedPage:
    text = _remove_blocks(wikitext.replace("\r\n", "\n"))
    text = _remove_tables(text)
    text, infobox_name, infobox = _remove_templates(text)
    lines = []
    for line in _clean(text).split("\n"):
        line = line.strip()
        if m := _HEADING.match(line):
            line = _tidy(m.group(2))
            if line:  # a heading that strips to nothing is just an empty line
                line = _HEADING_MARK + line
        else:
            line = _tidy(_LIST_MARKER.sub("", line))
        lines.append(line)
    prose = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
    head = "\n".join(f"{_key_label(k)}: {v}" for k, v in infobox.items() if v)
    prefix = head + "\n\n" if head and prose else head
    mark = prose.find(_HEADING_MARK)
    lead_end = len(prefix) + (mark if mark != -1 else len(prose))
    return StrippedPage(
        text=prefix + prose.replace(_HEADING_MARK, ""),
        infobox_name=infobox_name,
        infobox=infobox,
        lead_end=lead_end,
    )


_TYPE_KEYWORDS: list[tuple[EntryType, tuple[str, ...]]] = [
    ("character", ("character", "person", "deity")),
    ("place", ("location", "settlement", "place", "country", "city", "building")),
    ("faction", ("organization", "organisation", "faction", "military unit", "company")),
    ("item", ("weapon", "artifact", "artefact", "item")),
    ("event", ("event", "battle", "war")),
]


def type_from_infobox(name: str | None) -> EntryType | None:
    lowered = (name or "").lower()
    for entry_type, words in _TYPE_KEYWORDS:
        if any(word in lowered for word in words):
            return entry_type
    return None
