import json
import os
import re
import tempfile
import threading
from pathlib import Path

from sagaloom.models import World


class WorldRegistry:
    """The worlds in one JSON file. Every load-modify-save, and every read, runs under one lock
    (sync routes run in a thread pool, and on Windows `os.replace` fails while another thread
    has the file open); saves write a temp file and `os.replace` it, so a failed write leaves
    the old file intact."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._reserved: set[str] = set()  # ids handed out by `reserve_id`, not yet created

    def _load(self) -> list[World]:
        with self._lock:
            if not self.path.exists():
                return []
            return [World(**w) for w in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self, worlds: list[World]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(json.dumps([w.model_dump() for w in worlds], indent=2))
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise

    def _free_id(self, name: str, worlds: list[World]) -> str:
        """The registry's slug rule: the name's slug, then `-2`, `-3`, ... until unused."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "world"
        taken = {w.id for w in worlds} | self._reserved
        world_id, n = slug, 2
        while world_id in taken:
            world_id, n = f"{slug}-{n}", n + 1
        return world_id

    def reserve_id(self, name: str) -> str:
        """A fresh id for a world named `name` that no other create will take until the
        caller creates it with `world_id=` or calls `release`. For a world whose data is written
        before the world record (the demo copy)."""
        with self._lock:
            world_id = self._free_id(name, self._load())
            self._reserved.add(world_id)
            return world_id

    def release(self, world_id: str) -> None:
        with self._lock:
            self._reserved.discard(world_id)

    def all_worlds(self) -> list[World]:
        """Every world, whoever owns it: for startup and migration, never a user's listing."""
        return self._load()

    def owned_by(self, owner_id: str | None) -> list[World]:
        """The worlds of `owner_id`. Fails closed: `None` matches nothing, not ownerless worlds."""
        if owner_id is None:
            return []
        return [w for w in self._load() if w.owner_id == owner_id]

    def assign_unowned(self, owner_id: str) -> list[str]:
        """Gives every ownerless world to `owner_id`; returns the ids assigned."""
        with self._lock:
            worlds = self._load()
            assigned = [w.id for w in worlds if w.owner_id is None]
            if assigned:
                for w in worlds:
                    if w.owner_id is None:
                        w.owner_id = owner_id
                self._save(worlds)
            return assigned

    def get(self, id: str) -> World | None:
        return next((w for w in self._load() if w.id == id), None)

    def create(
        self,
        name: str,
        *,
        owner_id: str | None = None,
        world_id: str | None = None,
        is_demo: bool = False,
    ) -> World:
        with self._lock:
            worlds = self._load()
            if world_id is None:
                world_id = self._free_id(name, worlds)
            elif any(w.id == world_id for w in worlds):
                raise ValueError(f"World {world_id!r} already exists")
            world = World(id=world_id, name=name, is_demo=is_demo, owner_id=owner_id)
            self._save([*worlds, world])
            self._reserved.discard(world_id)
            return world

    # Defined last: below this line `list` in the class body names this method, not the builtin.
    def list(self, owner_id: str | None) -> list[World]:
        """Same as `owned_by`; the owner is required, so a forgotten owner cannot list every world."""
        return self.owned_by(owner_id)
