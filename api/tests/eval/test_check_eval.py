"""Recall/precision eval for the contradiction check (R4.9, R11.3.8).

Needs a real OpenRouter key. Excluded from the default run; run with:
    uv run pytest -m eval tests/eval/test_check_eval.py
"""

import json
import uuid
from pathlib import Path

import chromadb
import pytest

from sagaloom.check.contradiction import check_proposal
from sagaloom.config import Settings
from sagaloom.llm import make_chat_model, make_embeddings
from sagaloom.models import EntryDraft, Fact, Proposal
from sagaloom.seed import VELMAR_ID, load_seed
from sagaloom.store.canon import CanonStore, norm
from sagaloom.store.worlds import WorldRegistry

SEED = Path(__file__).resolve().parents[3] / "seed" / "velmar"
RUNS = 10
MIN_PASSES = 9


@pytest.mark.eval
async def test_scripted_contradictions_caught(tmp_path):
    settings = Settings()
    store = CanonStore(
        chromadb.EphemeralClient(),
        make_embeddings(settings),
        collection_name=f"eval_{uuid.uuid4().hex}",
    )
    load_seed(store, WorldRegistry(tmp_path / "worlds.json"), SEED)
    judge = make_chat_model(settings, model=settings.judge_model)
    scripted = json.loads((SEED / "scripted_proposals.json").read_text(encoding="utf-8"))

    report: dict[str, list[str]] = {}
    for sp in scripted:
        entry_id = sp.get("entry_id")
        proposal = Proposal(
            proposal_id=f"eval_{sp['name']}",
            action=sp["action"],
            world_id=VELMAR_ID,
            entry_id=entry_id,
            before=store.get_entry(VELMAR_ID, entry_id) if entry_id else None,
            after=EntryDraft(**sp["draft"]),
        )
        expected_ids = set(sp["expect"]["conflict_ids"])
        expected_retcons = {norm(k) for k in sp["expect"]["retcon_keys"]}
        passes = 0
        outcomes = []
        for _ in range(RUNS):
            res = await check_proposal(store, proposal, judge)
            conflict_ids = {f.entry_id for f in res.flags if f.kind == "conflict"}
            hard = [f for f in res.flags if f.kind == "conflict" and f.severity == "hard"]
            retcons = {norm(f.fact_key) for f in res.flags if f.kind == "retcon" and f.fact_key}
            assert retcons == expected_retcons, sp["name"]  # deterministic
            if expected_ids:
                ok = res.verdict != "failed" and expected_ids <= conflict_ids
            else:
                ok = res.verdict != "failed" and not hard
            passes += ok
            outcomes.append(f"{res.verdict}:{sorted(conflict_ids)}")
        report[sp["name"]] = outcomes
        assert passes >= MIN_PASSES, f"{sp['name']}: {passes}/{RUNS} passed; {outcomes}"
    print(json.dumps(report, indent=2))


def _create(name: str, title: str, type_: str, body: str, facts: list[tuple[str, str]]) -> Proposal:
    return Proposal(
        proposal_id=f"eval_{name}",
        action="create",
        world_id=VELMAR_ID,
        entry_id=None,
        before=None,
        after=EntryDraft(title=title, type=type_, body=body, facts=[Fact(key=k, value=v) for k, v in facts]),
    )


# R4.10: proposals that agree with the seed. Each carries one comment saying why it is consistent.
# Creates: new entries that mention seed entries without contradicting them.
CONSISTENT_CREATES = [
    # Ketra Dunn (ent_0017) is the head lamplighter of Lantern Quay; an apprentice adds no claim about her.
    (
        "lamplighter_apprentice", "Pell Marsh", "character",
        "Pell Marsh is the lamplighter's apprentice on Lantern Quay and carries the ladder for Ketra Dunn.",
        [("Role", "Apprentice lamplighter"), ("Works on", "Lantern Quay")],
    ),
    # The Salt Guild (ent_0011) holds the quay warehouses (ent_0010); a ledger of their rents fits that.
    (
        "salt_guild_ledger", "The Salt Guild Ledger", "item",
        "A bound ledger in which the Salt Guild records the rents of its warehouses on Lantern Quay.",
        [("Kept by", "The Salt Guild"), ("Records", "Warehouse rents on Lantern Quay")],
    ),
    # The Ashen Choir (ent_0004) meets at the Cinder Steps beneath the Tidehall (ent_0009); the entry says the same.
    (
        "cinder_steps", "The Cinder Steps", "place",
        "The Cinder Steps lead down from the Tidehall to the sea wall, where the Ashen Choir meets.",
        [("Beneath", "The Tidehall"), ("Used by", "The Ashen Choir")],
    ),
    # The Grey River (ent_0008) is forty leagues long and meets the sea at Velmar harbour; a ferry crossing it adds a use.
    (
        "river_ferry", "The Grey River Ferry", "item",
        "A flat-bottomed ferry that crosses the Grey River near its mouth, close to Velmar harbour.",
        [("Crosses", "The Grey River"), ("Crew", "Two ferrymen")],
    ),
    # Edric Vane (ent_0016) was drowned in 331 AF as Harbour-Warden; a character entry repeats those facts.
    (
        "edric_vane", "Edric Vane", "character",
        "Harbour-Warden Edric Vane kept the harbour mouth until he drowned in 331 AF.",
        [("Role", "Harbour-Warden"), ("Died", "331 AF")],
    ),
]

# Updates: each keeps every stored fact and adds one new key.
CONSISTENT_UPDATES = [
    ("ent_0010", ("Paving", "Grey cobbles")),  # Lantern Quay had no paving fact.
    ("ent_0002", ("Robes", "Grey wool")),  # The Harbour Council had no dress fact.
    ("ent_0014", ("Tone", "A low hum in the fog")),  # The Drowned Bell had no sound fact.
    ("ent_0017", ("Lodges at", "Lantern Quay")),  # Ketra Dunn tends the quay lanterns; a lodging there agrees.
    ("ent_0008", ("Fish", "Grey eels")),  # The Grey River had no fish fact.
]


@pytest.mark.eval
async def test_consistent_proposals_rarely_hard(tmp_path):
    """R4.10: ten proposals that agree with the seed raise at most one hard conflict flag in all."""
    settings = Settings()
    store = CanonStore(
        chromadb.EphemeralClient(),
        make_embeddings(settings),
        collection_name=f"eval_{uuid.uuid4().hex}",
    )
    load_seed(store, WorldRegistry(tmp_path / "worlds.json"), SEED)
    judge = make_chat_model(settings, model=settings.judge_model)

    proposals = [_create(*c) for c in CONSISTENT_CREATES]
    for entry_id, (key, value) in CONSISTENT_UPDATES:
        before = store.get_entry(VELMAR_ID, entry_id)
        proposals.append(
            Proposal(
                proposal_id=f"eval_update_{entry_id}",
                action="update",
                world_id=VELMAR_ID,
                entry_id=entry_id,
                before=before,
                after=EntryDraft(
                    title=before.title,
                    type=before.type,
                    body=before.body,
                    status=before.status,
                    aliases=before.aliases,
                    facts=[*before.facts, Fact(key=key, value=value)],
                ),
            )
        )
    assert len(proposals) == 10

    hard_flags = []
    for proposal in proposals:
        res = await check_proposal(store, proposal, judge)
        for f in res.flags:
            print(f"{proposal.proposal_id}: verdict={res.verdict} {f.kind}/{f.severity} {f.entry_id} {f.explanation}")
            if f.kind == "conflict" and f.severity == "hard":
                hard_flags.append((proposal.proposal_id, f))
        if not res.flags:
            print(f"{proposal.proposal_id}: verdict={res.verdict} no flags")
    print(f"hard conflict flags: {len(hard_flags)}")
    assert len(hard_flags) <= 1, f"{len(hard_flags)} hard flags on consistent proposals: {hard_flags}"
