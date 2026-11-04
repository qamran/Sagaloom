from sagaloom.models import Entry, EntryDraft, Fact, Flag
from sagaloom.store.canon import norm

_ESTABLISHED = ("canon", "secret")


def _group(facts: list[Fact]) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    for f in facts:
        if f.status in _ESTABLISHED:
            out.setdefault(norm(f.key), []).append(f)
    return out


def detect_retcons(before: Entry, after: EntryDraft) -> list[Flag]:
    old, new = _group(before.facts), _group(after.facts)
    flags: list[Flag] = []
    for key, old_facts in old.items():
        new_facts = new.get(key, [])
        if {norm(f.value) for f in old_facts} == {norm(f.value) for f in new_facts}:
            continue
        existing = ", ".join(f.value for f in old_facts)
        proposed = ", ".join(f.value for f in new_facts) if new_facts else None
        explanation = (
            f"Removes established canon: {existing}"
            if proposed is None
            else f"Changes established canon: {existing} → {proposed}"
        )
        flags.append(
            Flag(
                kind="retcon",
                entry_id=before.id,
                title=before.title,
                fact_key=old_facts[0].key,
                existing_fact=existing,
                new_fact=proposed,
                severity=None,
                explanation=explanation,
                existing_secret=before.status == "secret"
                or any(f.status == "secret" for f in old_facts),
            )
        )
    return flags
