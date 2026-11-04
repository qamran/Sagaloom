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
from sagaloom.models import EntryDraft, Proposal
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
