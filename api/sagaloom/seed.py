import json
from pathlib import Path

from sagaloom.models import Entry, World
from sagaloom.store.canon import CanonStore
from sagaloom.store.worlds import WorldRegistry

VELMAR_ID = "velmar"
VELMAR_NAME = "Velmar"


def load_seed(
    store: CanonStore, worlds: WorldRegistry, seed_dir: Path, world_id: str = VELMAR_ID
) -> int:
    """Upsert the seed entries (fixed IDs, so safe to repeat). Returns the entry count."""
    raw = json.loads((Path(seed_dir) / "entries.json").read_text(encoding="utf-8"))
    entries = [Entry(**{**r, "world_id": world_id}) for r in raw]
    if worlds.get(world_id) is None:
        worlds.create(VELMAR_NAME, world_id=world_id, is_demo=True)
    for e in entries:
        store.upsert_entry(e)
    return len(entries)


def ensure_first_run(store: CanonStore, worlds: WorldRegistry, seed_dir: Path) -> World:
    """Load Velmar only if no world exists; return the active world."""
    existing = worlds.list()
    if existing:
        return existing[0]
    load_seed(store, worlds, seed_dir)
    return worlds.get(VELMAR_ID)
