import json
import logging
from pathlib import Path

from sagaloom.models import Entry, World
from sagaloom.store.canon import CanonStore, norm
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


def seed_missing(
    store: CanonStore, seed_dir: Path, world_id: str = VELMAR_ID
) -> list[tuple[str, Entry]]:
    """Add the seed entries missing from the world, for data created before a seed entry was
    added. A seed entry is present when the world holds an entry with its title (at its seed
    id, or at the id an earlier run gave it); an existing entry is never overwritten. If the
    seed id is taken by another entry in any world (ids are global, so Captain Sorn may hold
    ent_0019), the seed entry is added under a fresh id; this is safe only for a seed entry
    nothing links to, such as the Choir Ledger. Returns (seed id, stored entry) pairs."""
    titles = {norm(e.title) for e in store.list_entries(world_id)}
    added = []
    for e in _seed_entries(seed_dir, world_id):
        if norm(e.title) in titles:
            continue
        seed_id = e.id
        if store.has_id(seed_id):
            e = e.model_copy(update={"id": store.next_entry_id()})
        stored = store.upsert_entry(e)
        titles.add(norm(stored.title))
        log.info("added %s as %s (%s)", seed_id, stored.id, stored.title)
        added.append((seed_id, stored))
    return added
