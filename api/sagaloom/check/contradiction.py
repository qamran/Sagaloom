"""Contradiction check (R11.3): facts first, then prose; fails closed (R11.3.7)."""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from sagaloom.check.dependency import dependency_check
from sagaloom.check.duplicate import duplicate_flags
from sagaloom.check.prompts import JUDGE_SYSTEM
from sagaloom.check.retcon import detect_retcons
from sagaloom.models import CheckResult, Entry, EntryDraft, Fact, Flag, Proposal
from sagaloom.security import wrap_untrusted
from sagaloom.store.canon import norm
from sagaloom.structured import ChatModelLike, InvalidReply, ask_structured

log = logging.getLogger(__name__)

SEARCH_K = 8
_BELIEFS = ("myth", "rumour")
CHECK_FAILED_EXPLANATION = (
    "The contradiction check could not run, so clashes with other entries are unknown. "
    "Review this change carefully before approving it."
)


class JudgeFlag(BaseModel):
    entry_id: str = Field(description="ID of the EXISTING related entry, e.g. ent_0012")
    fact_key: str | None = Field(
        description="Key of the PROPOSED fact involved, or null for a prose-only clash"
    )
    existing: str = Field(
        description='Existing fact as "<key>: <value>", or a verbatim quote from its body'
    )
    proposed: str = Field(
        description='Proposed fact as "<key>: <value>", or a verbatim quote from the proposal'
    )
    severity: Literal["hard", "possible"]
    explanation: str
    suggested_fix: str | None


class JudgeOutput(BaseModel):
    flags: list[JudgeFlag]


# ---------- retrieval ----------


def _related_entries(store, proposal: Proposal, draft: EntryDraft) -> list[Entry]:
    world = proposal.world_id
    by_id = {e.id: e for e in store.list_entries(world)}
    ids: set[str] = set()
    ids.update(h.id for h in store.search(world, f"{draft.title} {draft.body}", k=SEARCH_K))
    mention_text = "\n".join(
        [draft.title, *draft.aliases, draft.body, *(f"{f.key} {f.value}" for f in draft.facts)]
    )
    ids.update(e.id for e in store.mentioned_in(world, mention_text))
    keys = {norm(f.key) for f in draft.facts}
    ids.update(e.id for e in by_id.values() if any(norm(f.key) in keys for f in e.facts))
    ids.discard(proposal.entry_id)
    return [by_id[i] for i in sorted(ids) if i in by_id]


# ---------- prompt ----------


def _fact_line(f: Fact) -> str:
    told = f" (told by {f.told_by})" if f.told_by else ""
    return f"{f.key}: {f.value} [{f.status}]{told}"


def _render(title: str, type_: str, status: str, aliases: list[str], facts: list[Fact], body: str) -> str:
    lines = [f"Title: {title}", f"Type: {type_}", f"Entry status: {status}"]
    if aliases:
        lines.append("Aliases: " + ", ".join(aliases))
    lines.append("Facts:")
    lines.extend(f"- {_fact_line(f)}" for f in facts)
    if not facts:
        lines.append("- (none)")
    lines.append("Body:")
    lines.append(body)
    return "\n".join(lines)


UNTRUSTED_LABEL = " (untrusted source)"


def _label(trusted: bool) -> str:
    """Marks text that came from imported or reference sources (R13.6); trusted text has none."""
    return "" if trusted else UNTRUSTED_LABEL


def _build_prompt(proposal: Proposal, draft: EntryDraft, related: list[Entry]) -> str:
    what = "a change to entry " + proposal.entry_id if proposal.action == "update" else "a new entry"
    parts = [
        f"# Proposal ({what}){_label(draft.trusted)}",
        "Facts marked [myth] or [rumour] are in-world beliefs, not facts about the world.",
        wrap_untrusted(
            _render(draft.title, draft.type, draft.status, draft.aliases, draft.facts, draft.body),
            source="proposal",
        ),
        "",
        "# Pass 1: candidate fact pairs (same key)",
    ]
    any_pairs = False
    for e in related:
        pairs = [
            (pf, ef)
            for pf in draft.facts
            for ef in e.facts
            if norm(pf.key) == norm(ef.key)
        ]
        if not pairs:
            continue
        any_pairs = True
        text = "\n".join(
            f"Proposed: {_fact_line(pf)}\nExisting: {_fact_line(ef)} (entry status: {e.status})"
            for pf, ef in pairs
        )
        parts += [f"## Pairs with entry {e.id}{_label(e.trusted)}", wrap_untrusted(text, source=e.id)]
    if not any_pairs:
        parts.append("(No existing fact shares a key with the proposal; check similar keys in pass 2.)")
    parts += ["", "# Pass 2: related entries (all facts, then prose)"]
    for e in related:
        parts += [
            f"## Entry {e.id}{_label(e.trusted)}",
            wrap_untrusted(_render(e.title, e.type, e.status, e.aliases, e.facts, e.body), source=e.id),
        ]
    parts += [
        "",
        "Report every contradiction between the proposal and these entries as a JudgeOutput. "
        "Use only the entry IDs listed above.",
    ]
    return "\n".join(parts)


# ---------- judge ----------


# ---------- post-processing ----------


def _existing_facts(entry: Entry, existing: str, key: str | None) -> list[Fact]:
    ex = norm(existing)
    found = [f for f in entry.facts if norm(f"{f.key}: {f.value}") == ex]
    found = found or [f for f in entry.facts if norm(f.value) == ex]
    if not found and ":" in existing:
        k = norm(existing.split(":", 1)[0])
        found = [f for f in entry.facts if norm(f.key) == k]
    if not found and key:
        found = [f for f in entry.facts if norm(f.key) == key]
    return found


def _to_flag(jf: JudgeFlag, entry: Entry, draft: EntryDraft) -> Flag:
    key = norm(jf.fact_key) if jf.fact_key else None
    proposed = [f for f in draft.facts if key and norm(f.key) == key]
    if not proposed and ":" in jf.proposed:
        # The judge may name the existing key; recover ours from "<proposed key>: <value>".
        prefix = norm(jf.proposed.split(":", 1)[0])
        proposed = [f for f in draft.facts if norm(f.key) == prefix]
    existing = _existing_facts(entry, jf.existing, key)
    is_belief = (
        draft.status in _BELIEFS
        or entry.status in _BELIEFS
        or (proposed and all(f.status in _BELIEFS for f in proposed))
        or (existing and all(f.status in _BELIEFS for f in existing))
    )
    is_fact = bool(proposed)  # a key the proposal doesn't have is treated as a prose clash
    # Quote the store, not the judge's paraphrase, when the cited fact is unambiguous (R4.3).
    existing_fact = f"{existing[0].key}: {existing[0].value}" if len(existing) == 1 else jf.existing
    # The judge's free text may restate a secret: mark the flag so the card hides it (R12.12).
    # An unresolved citation is treated as secret if the entry holds any secret fact.
    existing_secret = (
        entry.status == "secret"
        or any(f.status == "secret" for f in existing)
        or (not existing and any(f.status == "secret" for f in entry.facts))
    )
    return Flag(
        kind="note" if is_belief else "conflict",
        entry_id=entry.id,
        title=entry.title,
        fact_key=proposed[0].key if is_fact else None,
        existing_fact=existing_fact if is_fact else None,
        new_fact=jf.proposed if is_fact else None,
        existing_quote=None if is_fact else jf.existing,
        new_quote=None if is_fact else jf.proposed,
        severity="note" if is_belief else jf.severity,
        explanation=jf.explanation,
        suggested_fix=jf.suggested_fix,
        existing_secret=existing_secret,
    )


def _failed(proposal: Proposal, draft: EntryDraft, retcons: list[Flag], dups: list[Flag]) -> CheckResult:
    notice = Flag(
        kind="note",
        entry_id=proposal.entry_id or "",
        title=draft.title,
        severity="note",
        explanation=CHECK_FAILED_EXPLANATION,
    )
    return CheckResult(
        proposal_id=proposal.proposal_id, verdict="failed", flags=[*retcons, notice, *dups]
    )


def _duplicates(store, proposal: Proposal, draft: EntryDraft) -> list[Flag]:
    """Duplicate notes for a create (spec §3.9). A note only, so a failure here costs the note,
    never the check."""
    if proposal.action != "create":
        return []
    try:
        return duplicate_flags(store, proposal.world_id, draft)
    except Exception:
        log.exception("Duplicate check failed for %s", proposal.proposal_id)
        return []


async def check_proposal(
    store, proposal: Proposal, judge: ChatModelLike, *, duplicates: bool = True
) -> CheckResult:
    if proposal.action == "delete":
        return dependency_check(store, proposal)
    draft = proposal.after
    if draft is None:
        raise ValueError(f"A {proposal.action} proposal needs a proposed entry")

    before = proposal.before
    if proposal.action == "update" and before is None and proposal.entry_id:
        before = store.get_entry(proposal.world_id, proposal.entry_id)
    retcons = detect_retcons(before, draft) if proposal.action == "update" and before else []
    dups = _duplicates(store, proposal, draft) if duplicates else []

    try:
        related = _related_entries(store, proposal, draft)
    except Exception:
        log.exception("Contradiction check retrieval failed for %s", proposal.proposal_id)
        return _failed(proposal, draft, retcons, dups)

    if not related:
        return CheckResult(proposal_id=proposal.proposal_id, verdict="none", flags=[*retcons, *dups])

    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=_build_prompt(proposal, draft, related)),
    ]
    try:
        out = await ask_structured(
            judge, JudgeOutput, messages, what="Judge", retry_transient=False
        )
    except InvalidReply:
        log.error("Judge gave invalid output twice for %s; failing closed", proposal.proposal_id)
        return _failed(proposal, draft, retcons, dups)
    except Exception:
        # Network/API errors after the client's own retries: never report "none" (R11.3.7).
        log.exception("Judge call failed for %s; failing closed", proposal.proposal_id)
        return _failed(proposal, draft, retcons, dups)

    by_id = {e.id: e for e in related}
    flags: list[Flag] = []
    for jf in out.flags:
        entry = by_id.get(jf.entry_id.strip())
        if entry is None:
            log.warning("Dropping judge flag for unrelated entry %r", jf.entry_id)
            continue
        flags.append(_to_flag(jf, entry, draft))

    conflicts = [f for f in flags if f.kind == "conflict"]
    if any(f.severity == "hard" for f in conflicts):
        verdict = "conflict"
    elif conflicts:
        verdict = "possible"
    else:
        verdict = "none"
    return CheckResult(proposal_id=proposal.proposal_id, verdict=verdict, flags=[*retcons, *flags, *dups])
