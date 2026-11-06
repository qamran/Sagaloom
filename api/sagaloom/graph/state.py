"""Graph state (R18) and its reducers."""

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

from sagaloom.models import CheckResult, Decision, MemoryUpdate, Proposal

# `router` runs on the guard's model (make_model_for aliases it) and is not switchable in Studio.
Role = Literal["agent", "judge", "extractor", "guard", "router"]
Mode = Literal["brainstorm", "query", "edit"]
GuardVerdictValue = Literal["safe", "unsafe", "injection", "error", "off"]


def merge_proposals(left: list[Proposal] | None, right: Any) -> list[Proposal]:
    """Reducer for `pending_proposals`. Pure: never mutates its inputs.

    - a list appends; a proposal whose id is already pending replaces it in place
      (this is how an edit swaps in the new `after`)
    - a proposal for an entry that already has a pending proposal replaces that one in place and
      keeps its id, so one entry is one card (parallel tool calls in one AI message share one
      state snapshot, so only the reducer sees both)
    - `{"clear": [ids]}` removes the proposals with those ids
    """
    current = list(left or [])
    if isinstance(right, dict):
        drop = set(right.get("clear", []))
        return [p for p in current if p.proposal_id not in drop]
    for p in right or []:
        idx = next((i for i, q in enumerate(current) if q.proposal_id == p.proposal_id), None)
        if idx is None and p.entry_id is not None:
            idx = next((i for i, q in enumerate(current) if q.entry_id == p.entry_id), None)
            if idx is not None:
                p = p.model_copy(update={"proposal_id": current[idx].proposal_id})
        if idx is None:
            current.append(p)
        else:
            current[idx] = p
    return current


def merge_dict(left: dict | None, right: dict | None) -> dict:
    """Reducer for keyed maps. Pure. A value of None deletes that key."""
    out = dict(left or {})
    for k, v in (right or {}).items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def merge_memory(left: list[MemoryUpdate] | None, right: list[MemoryUpdate] | None) -> list:
    """Reducer for `memory_updates`. Pure. A list appends (parallel `remember_preference` calls in
    one AI message all arrive); None resets it to [] (the `remember` node clears what it read)."""
    if right is None:
        return []
    return [*(left or []), *right]


class SagaState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    world_id: str
    pending_proposals: Annotated[list[Proposal], merge_proposals]
    check_results: Annotated[dict[str, CheckResult], merge_dict]
    # Only approve/reject are stored; edit and save_as_myth are applied at the gate
    # and the proposal is asked about again after its re-check.
    decisions: Annotated[dict[str, Decision], merge_dict]
    # This turn's input-guard result (R13.1); `off` when the guard is switched off in Studio.
    # Token usage is not kept in state: the prompt log is the only usage source (R12).
    guard_verdict: GuardVerdictValue
    # This turn's router mode (R6.5); None when the router call failed (the turn runs anyway).
    mode: Mode | None
    # Preferences queued by `remember_preference` this step; only the `remember` node writes
    # them to the Store, after the verbatim gate (R10.2), and then clears the list.
    memory_updates: Annotated[list[MemoryUpdate], merge_memory]
