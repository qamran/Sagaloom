import json
import logging
from pathlib import Path

from sagaloom.models import Entry, World
from sagaloom.store.canon import CanonStore, DuplicateTitleError
from sagaloom.store.worlds import WorldRegistry

VELMAR_ID = "velmar"
VELMAR_NAME = "Velmar"

log = logging.getLogger(__name__)


def _seed_entries(seed_dir: Path, world_id: str) -> list[Entry]:
    raw = json.loads((Path(seed_dir) / "entries.json").read_text(encoding="utf-8"))
    return [Entry(**{**r, "world_id": world_id}) for r in raw]


def load_seed(
    store: CanonStore, worlds: WorldRegistry, seed_dir: Path, world_id: str = VELMAR_ID
) -> int:
    """Upsert the seed entries (fixed IDs, so safe to repeat). Returns the entry count."""
    entries = _seed_entries(seed_dir, world_id)
    for e in entries:
        store.upsert_entry(e)
    # The world is the "seed committed" marker: create it only after every upsert succeeded.
    if worlds.get(world_id) is None:
        worlds.create(VELMAR_NAME, world_id=world_id, is_demo=True)
    return len(entries)


def ensure_first_run(store: CanonStore, worlds: WorldRegistry, seed_dir: Path) -> World:
    """Load Velmar only if no world exists; return the active world."""
    existing = worlds.list()
    if existing:
        return existing[0]
    load_seed(store, worlds, seed_dir)
    return worlds.get(VELMAR_ID)


def seed_missing(store: CanonStore, seed_dir: Path, world_id: str = VELMAR_ID) -> list[str]:
    """Add only the seed entries absent from the world (for data created before a seed entry
    was added); an entry the author edited or kept is never touched. An id or title that is
    taken elsewhere (entry ids are global across worlds) is skipped. Returns the ids added."""
    added = []
    for e in _seed_entries(seed_dir, world_id):
        if store.get_entry(world_id, e.id) is not None:
            continue
        try:
            store.upsert_entry(e)
        except (DuplicateTitleError, ValueError) as exc:
            log.warning("skipped seed entry %s: %s", e.id, exc)
            continue
        added.append(e.id)
    return added
