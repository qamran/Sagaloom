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

    def list(self) -> list[World]:
        return self._load()

    def get(self, id: str) -> World | None:
        return next((w for w in self._load() if w.id == id), None)

    def create(self, name: str, *, world_id: str | None = None, is_demo: bool = False) -> World:
        worlds = self._load()
        if world_id is None:
            slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "world"
            world_id, n = slug, 2
            while any(w.id == world_id for w in worlds):
                world_id, n = f"{slug}-{n}", n + 1
        elif any(w.id == world_id for w in worlds):
            raise ValueError(f"World {world_id!r} already exists")
        world = World(id=world_id, name=name, is_demo=is_demo)
        worlds.append(world)
        self._save(worlds)
        return world
