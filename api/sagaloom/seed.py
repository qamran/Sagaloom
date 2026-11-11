import json
import logging
from dataclasses import dataclass, field
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


def _names(e: Entry) -> set[str]:
    return {norm(n) for n in [e.title, *e.aliases]} - {""}


@dataclass
class SeedReport:
    """What `seed_missing` did. `added`: (seed id, stored entry). `kept`: (seed id, the
    same-type entry already at that id), a seed entry treated as present under rule (b)."""

    added: list[tuple[str, Entry]] = field(default_factory=list)
    kept: list[tuple[str, Entry]] = field(default_factory=list)


def seed_missing(store: CanonStore, seed_dir: Path, world_id: str = VELMAR_ID) -> SeedReport:
    """Add the seed entries missing from the world, for data created before a seed entry was
    added. An existing entry is never overwritten.

    A seed entry is present when either
    (a) an entry in the world has a title or alias matching the seed entry's title or any
        alias (normalised with `norm`, as `find_by_name` does); this also finds an entry an
        earlier run added under a fresh id; or
    (b) the entry at the seed id in this world has the seed entry's type (a renamed seed
        entry).
    Otherwise it is missing. It is added at its seed id if this world does not hold that id,
    or under `next_entry_id(world_id)` if the id is taken (ids are unique per world; Captain
    Sorn, a character, may hold ent_0019 while the ledger is an item). A fresh id is safe only
    for a seed entry nothing links to, such as the Choir Ledger. Returns a SeedReport: the
    additions and the rule (b) entries kept."""
    names: set[str] = set()
    for existing in store.list_entries(world_id):
        names |= _names(existing)
    report = SeedReport()
    for e in _seed_entries(seed_dir, world_id):
        if _names(e) & names:
            continue
        at_id = store.get_entry(world_id, e.id)
        if at_id is not None and at_id.type == e.type:
            report.kept.append((e.id, at_id))
            continue
        seed_id = e.id
        if store.has_id(world_id, seed_id):
            e = e.model_copy(update={"id": store.next_entry_id(world_id)})
        stored = store.upsert_entry(e)
        names |= _names(stored)
        log.info("added %s as %s (%s)", seed_id, stored.id, stored.title)
        report.added.append((seed_id, stored))
    return report
