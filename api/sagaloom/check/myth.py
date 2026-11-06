from sagaloom.models import CheckResult, Entry, EntryDraft, Fact, Proposal
from sagaloom.store.canon import norm

_ESTABLISHED = ("canon", "secret")


def _renamed(before: Entry | None, after: EntryDraft, result: CheckResult):
    """A test for a proposed fact under a key `before` does not have: does a flag point at it?
    Either a conflict/retcon flag quotes it, or the change removed a key and this fact carries
    a value that key never held (the old value moved under a new name stays canon)."""
    if before is None:
        return lambda f: False
    keys = {norm(f.key) for f in before.facts}
    quoted = {
        norm(f.new_fact)
        for f in result.flags
        if f.kind in ("conflict", "retcon") and f.new_fact is not None
    }
    stored: dict[str, set[str]] = {}
    for s in before.facts:
        if s.status in _ESTABLISHED:
            stored.setdefault(norm(s.key), set()).add(norm(s.value))
    # A retcon with no new value is per stored fact: the key is removed only when the
    # proposal no longer has it at all.
    proposed_keys = {norm(f.key) for f in after.facts}
    removed = [
        stored.get(norm(f.fact_key), set())
        for f in result.flags
        if f.kind == "retcon"
        and f.new_fact is None
        and f.fact_key
        and norm(f.fact_key) not in proposed_keys
    ]

    def flagged(f: Fact) -> bool:
        if norm(f.key) in keys:
            return False
        value = norm(f.value)
        if value in quoted or norm(f"{f.key}: {f.value}") in quoted:
            return True
        return any(value not in held for held in removed)

    return flagged


def apply_save_as_myth(
    proposal: Proposal, result: CheckResult, told_by: str | None
) -> EntryDraft:
    if proposal.after is None:
        raise ValueError("Save as myth needs a proposed entry")
    before = proposal.before
    flagged = {
        norm(f.fact_key)
        for f in result.flags
        if f.kind in ("conflict", "retcon") and f.fact_key
    }
    renamed = _renamed(before, proposal.after, result)
    kept: dict[str, list[Fact]] = {}
    if before is not None:
        for f in before.facts:
            if f.status in ("canon", "secret") and norm(f.key) in flagged:
                kept.setdefault(norm(f.key), []).append(f)

    facts: list[Fact] = []
    restored: set[str] = set()

    def restore(key: str) -> None:
        if key in kept and key not in restored:
            restored.add(key)
            facts.extend(f.model_copy(deep=True) for f in kept[key])

    for f in proposal.after.facts:
        key = norm(f.key)
        if renamed(f):
            facts.append(f.model_copy(update={"status": "myth", "told_by": told_by}, deep=True))
            continue
        if key not in flagged:
            facts.append(f.model_copy(deep=True))
            continue
        restore(key)
        if any(norm(k.value) == norm(f.value) for k in kept.get(key, [])):
            continue  # unchanged canon value, already restored
        facts.append(f.model_copy(update={"status": "myth", "told_by": told_by}, deep=True))
    for key in kept:
        restore(key)

    body = before.body if before is not None and proposal.action == "update" else proposal.after.body
    return proposal.after.model_copy(update={"facts": facts, "body": body}, deep=True)
