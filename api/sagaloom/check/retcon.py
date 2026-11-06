from sagaloom.models import Entry, EntryDraft, Fact, Flag
from sagaloom.store.canon import norm

_ESTABLISHED = ("canon", "secret")


def _group(facts: list[Fact]) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    for f in facts:
        if f.status in _ESTABLISHED:
            out.setdefault(norm(f.key), []).append(f)
    return out


def _flag(before: Entry, fact: Fact, new_fact: str | None, explanation: str, secret: bool) -> Flag:
    return Flag(
        kind="retcon",
        entry_id=before.id,
        title=before.title,
        fact_key=fact.key,
        existing_fact=fact.value,
        new_fact=new_fact,
        severity=None,
        explanation=explanation,
        existing_secret=before.status == "secret" or secret,
    )


def detect_retcons(before: Entry, after: EntryDraft) -> list[Flag]:
    """One flag per stored established fact the change drops, so a flag never mixes a secret
    value with a canon one; a key that only gains values gets one flag."""
    old, new = _group(before.facts), _group(after.facts)
    flags: list[Flag] = []
    for key, old_facts in old.items():
        new_facts = new.get(key, [])
        old_values = {norm(f.value) for f in old_facts}
        new_values = {norm(f.value) for f in new_facts}
        if old_values == new_values:
            continue
        added = ", ".join(f.value for f in new_facts if norm(f.value) not in old_values) or None
        dropped = [f for f in old_facts if norm(f.value) not in new_values]
        for f in dropped:
            explanation = (
                f"Removes established canon: {f.value}"
                if added is None
                else f"Changes established canon: {f.value} → {added}"
            )
            flags.append(_flag(before, f, added, explanation, f.status == "secret"))
        if not dropped:
            secret = any(f.status == "secret" for f in old_facts)
            flags.append(
                _flag(before, old_facts[0], added, f"Adds to established canon: {added}", secret)
            )
    return flags
