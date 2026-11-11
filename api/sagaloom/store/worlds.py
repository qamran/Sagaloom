import json
import os
import re
import secrets
import string
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from sagaloom.models import World

# On a slug collision: `-` and this many random lowercase letters and digits (spec §5.4).
SUFFIX_LEN = 4
_SUFFIX_ALPHABET = string.ascii_lowercase + string.digits


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

    def _free_id(
        self, name: str, worlds: list[World], in_use: Callable[[str], bool] | None = None
    ) -> str:
        """The registry's slug rule (spec §5.4): the name's slug, or on a collision the slug and
        `-` plus `SUFFIX_LEN` random lowercase letters and digits (drawn again until free), never
        a counter, so an id tells nothing about other accounts' worlds. A candidate is taken
        when a world or a reservation holds it, or when `in_use(id)` says so (the canon store
        still holds records under it, e.g. after a lost worlds.json)."""
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "world"
        taken = {w.id for w in worlds} | self._reserved

        def free(world_id: str) -> bool:
            return world_id not in taken and not (in_use is not None and in_use(world_id))

        world_id = slug
        while not free(world_id):
            world_id = f"{slug}-" + "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(SUFFIX_LEN))
        return world_id

    def reserve_id(self, name: str, *, in_use: Callable[[str], bool] | None = None) -> str:
        """A fresh id for a world named `name` that no other create will take until the
        caller creates it with `world_id=` or calls `release`. For a world whose data is written
        before the world record (the demo copy)."""
        with self._lock:
            world_id = self._free_id(name, self._load(), in_use)
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

    def reassign_owner(self, old_owner_id: str, new_owner_id: str) -> list[str]:
        """Gives every world of `old_owner_id` to `new_owner_id` (`scripts/reassign_owner.py`);
        returns the ids moved."""
        with self._lock:
            worlds = self._load()
            moved = [w.id for w in worlds if w.owner_id == old_owner_id]
            if moved:
                for w in worlds:
                    if w.owner_id == old_owner_id:
                        w.owner_id = new_owner_id
                self._save(worlds)
            return moved

    def get(self, id: str) -> World | None:
        return next((w for w in self._load() if w.id == id), None)

    def create(
        self,
        name: str,
        *,
        owner_id: str | None = None,
        world_id: str | None = None,
        is_demo: bool = False,
        in_use: Callable[[str], bool] | None = None,
    ) -> World:
        """A new world. Without `world_id`, a free id by the slug rule (`_free_id`, which also
        skips ids `in_use` reports)."""
        with self._lock:
            worlds = self._load()
            if world_id is None:
                world_id = self._free_id(name, worlds, in_use)
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
