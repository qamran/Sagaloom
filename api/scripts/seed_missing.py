"""Add the Velmar seed entries that are missing from an existing `velmar` world.

Use it after a new seed entry ships (such as ent_0019, The Choir Ledger): first-run seeding
only happens when no world exists, so older data never gets it. Entries already in the world,
including any the author edited, are left alone.

Stop the API first: it holds the same Chroma directory open. The store is built exactly as at
app startup; `Settings()` reads api/.env itself.

    cd api && uv run python scripts/seed_missing.py
"""

from pathlib import Path

import chromadb

from sagaloom.config import Settings
from sagaloom.llm import make_embeddings
from sagaloom.seed import VELMAR_ID, seed_missing
from sagaloom.store.canon import CanonStore
from sagaloom.store.worlds import WorldRegistry

# The same directory as sagaloom.web.app.SEED_DIR; importing the app module would build the app.
SEED_DIR = Path(__file__).resolve().parents[2] / "seed" / "velmar"


def main() -> None:
    settings = Settings()
    worlds = WorldRegistry(Path(settings.data_dir) / "worlds.json")
    if worlds.get(VELMAR_ID) is None:
        print(f"no '{VELMAR_ID}' world in {settings.data_dir}; nothing to do")
        return
    client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    store = CanonStore(client, make_embeddings(settings))
    added = seed_missing(store, SEED_DIR)
    for seed_id, entry in added:
        print(f"added {seed_id} as {entry.id} ({entry.title})")
    if not added:
        print("nothing missing")


if __name__ == "__main__":
    main()
