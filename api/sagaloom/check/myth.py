from sagaloom.models import CheckResult, EntryDraft, Fact, Proposal
from sagaloom.store.canon import norm


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
