"""Graph state (R18) and its reducers."""

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages

from sagaloom.models import CheckResult, Decision, Proposal, Usage
from sagaloom.usage import add_usage

Role = Literal["agent", "judge", "extractor", "guard"]


def merge_proposals(left: list[Proposal] | None, right: Any) -> list[Proposal]:
    """Reducer for `pending_proposals`. Pure: never mutates its inputs.

    - a list appends; a proposal whose id is already pending replaces it in place
      (this is how an edit swaps in the new `after`)
    - `{"clear": [ids]}` removes the proposals with those ids
    """
    current = list(left or [])
    if isinstance(right, dict):
        drop = set(right.get("clear", []))
        return [p for p in current if p.proposal_id not in drop]
    for p in right or []:
        idx = next((i for i, q in enumerate(current) if q.proposal_id == p.proposal_id), None)
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


class SagaState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    world_id: str
    pending_proposals: Annotated[list[Proposal], merge_proposals]
    check_results: Annotated[dict[str, CheckResult], merge_dict]
    # Only approve/reject are stored; edit and save_as_myth are applied at the gate
    # and the proposal is asked about again after its re-check.
    decisions: Annotated[dict[str, Decision], merge_dict]
    token_usage: Annotated[Usage, add_usage]
