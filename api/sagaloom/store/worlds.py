import json
import re
from pathlib import Path

from sagaloom.models import World


class WorldRegistry:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> list[World]:
        if not self.path.exists():
            return []
        return [World(**w) for w in json.loads(self.path.read_text(encoding="utf-8"))]

    def _save(self, worlds: list[World]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([w.model_dump() for w in worlds], indent=2), encoding="utf-8"
        )

    def owned_by(self, owner_id: str) -> list[World]:
        return self.list(owner_id=owner_id)

    def assign_unowned(self, owner_id: str) -> list[str]:
        """Gives every ownerless world to `owner_id`; returns the ids assigned."""
        worlds = self._load()
        assigned = [w.id for w in worlds if w.owner_id is None]
        if assigned:
            for w in worlds:
                if w.owner_id is None:
                    w.owner_id = owner_id
            self._save(worlds)
        return assigned

    def list(self, owner_id: str | None = None) -> list[World]:
        worlds = self._load()
        if owner_id is None:
            return worlds
        return [w for w in worlds if w.owner_id == owner_id]

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
        worlds = self._load()
        if world_id is None:
            slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "world"
            world_id, n = slug, 2
            while any(w.id == world_id for w in worlds):
                world_id, n = f"{slug}-{n}", n + 1
        elif any(w.id == world_id for w in worlds):
            raise ValueError(f"World {world_id!r} already exists")
        world = World(id=world_id, name=name, is_demo=is_demo, owner_id=owner_id)
        worlds.append(world)
        self._save(worlds)
        return world
