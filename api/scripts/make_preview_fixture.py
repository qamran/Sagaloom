"""Make the logged-out home page's frozen Velmar example (`sagaloom/public/preview.json`).

Runs the real graph once, on real models, in a throwaway data dir seeded with Velmar (it never
touches `api/data`): the author states a fact that conflicts with canon, the turn stops at the
approval card, and the thread state plus four entries are written, with every secret entry and
secret fact removed. It costs a few cents. Re-run it when the seed or the graph changes.

    cd api && uv run python scripts/make_preview_fixture.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import chromadb
from fastapi.encoders import jsonable_encoder
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from sagaloom.config import Settings, load_env_files
from sagaloom.graph.build import build_graph, checkpoint_serde, run_config
from sagaloom.llm import install_warning_filters, make_embeddings
from sagaloom.model_settings import ModelSettings
from sagaloom.seed import VELMAR_ID, load_seed
from sagaloom.store.canon import CanonStore
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.app import SEED_DIR, make_model_for
from sagaloom.web.routes import message_dict
from sagaloom.web.thread_list import pending_interrupt

OUT = Path(__file__).resolve().parents[1] / "sagaloom" / "public" / "preview.json"
MESSAGE = "Velmar has three moons that rise together at the solstice."
# Sky of Velmar, Ister the red moon, Lantern Quay, The Harbour Council.
ENTRY_IDS = ["ent_0007", "ent_0012", "ent_0010", "ent_0002"]
# Text that must appear nowhere in the file: the secret entry and the Mayor's secret fact.
FORBIDDEN = ["Choir Ledger", "Yes, at every full Ister"]


def strip_secrets(entry: dict) -> dict:
    return {**entry, "facts": [f for f in entry["facts"] if f.get("status") != "secret"]}


def cites_ister(checks: dict) -> bool:
    """A card with a conflict flag that points at Ister (ent_0012)."""
    return any(
        c["verdict"] == "conflict" and any(f["entry_id"] == "ent_0012" for f in c["flags"])
        for c in checks.values()
    )


async def run_once(tmp: Path) -> dict:
    settings = Settings(data_dir=tmp)
    store = CanonStore(chromadb.PersistentClient(path=str(tmp / "chroma")), make_embeddings(settings))
    worlds = WorldRegistry(tmp / "worlds.json")
    load_seed(store, worlds, SEED_DIR)
    model_for = make_model_for(settings, ModelSettings(tmp / "model_settings.json", settings))
    graph = build_graph(store=store, model_for=model_for, checkpointer=InMemorySaver(serde=checkpoint_serde()))
    cfg = run_config("preview", VELMAR_ID)
    await graph.ainvoke(
        {"messages": [HumanMessage(content=MESSAGE)], "world_id": VELMAR_ID, "entry": "chat"}, cfg
    )
    state = await graph.aget_state(cfg)
    interrupt = pending_interrupt(state)
    if not interrupt:
        raise RuntimeError("the turn did not stop at an approval card")
    entries = [e for e in store.list_entries(VELMAR_ID) if e.id in ENTRY_IDS and e.status != "secret"]
    return {
        "messages": [message_dict(m) for m in state.values["messages"]],
        "pending_interrupt": {"proposals": interrupt["proposals"], "checks": interrupt["checks"]},
        "entries": [strip_secrets(e) for e in jsonable_encoder(entries)],
    }


def verify(data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False)
    for s in FORBIDDEN:
        if s in text:
            raise RuntimeError(f"secret text in the fixture: {s!r}")
    if sorted(e["id"] for e in data["entries"]) != sorted(ENTRY_IDS):
        raise RuntimeError("the four entries are not all there")
    if any(e["status"] == "secret" or any(f.get("status") == "secret" for f in e["facts"]) for e in data["entries"]):
        raise RuntimeError("a secret survived")


def main() -> None:
    load_env_files()
    install_warning_filters()
    tries = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for attempt in range(1, tries + 1):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            data = asyncio.run(run_once(Path(d)))
        ok = cites_ister(data["pending_interrupt"]["checks"])
        print(f"try {attempt}: conflict with ent_0012: {ok}")
        if ok:
            verify(data)
            OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"wrote {OUT}")
            return
    sys.exit(f"no card cited ent_0012 in {tries} tries; nothing written")


if __name__ == "__main__":
    main()
