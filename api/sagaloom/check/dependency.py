from sagaloom.models import CheckResult, EntryRef, Proposal


def dependency_check(store, proposal: Proposal) -> CheckResult:
    entry = proposal.before
    if entry is None and proposal.entry_id is not None:
        entry = store.get_entry(proposal.world_id, proposal.entry_id)
    mentions = store.find_mentions(proposal.world_id, entry) if entry else []
    return CheckResult(
        proposal_id=proposal.proposal_id,
        verdict="none",
        flags=[],
        dependents=[EntryRef(id=e.id, title=e.title, type=e.type) for e in mentions],
    )
