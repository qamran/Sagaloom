"""Developer settings (R12.4): persisted to `data/settings.json` and read on every call, so a
change applies from the next turn. Judge, extractor and guard temperatures are not editable."""

import json
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DevSettings(BaseModel):
    agent_temperature: float = Field(default=0.0, ge=0, le=2)
    agent_max_tokens: int | None = Field(default=None, ge=256, le=16000)
    agent_system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    guard_enabled: bool = True


class DevSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_temperature: float | None = Field(default=None, ge=0, le=2)
    agent_max_tokens: int | None = Field(default=None, ge=256, le=16000)
    agent_system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    guard_enabled: bool | None = None
    reset_system_prompt: bool = False


class DevSettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def get(self) -> DevSettings:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return DevSettings()
        if not isinstance(saved, dict):
            return DevSettings()
        good: dict = {}
        for name in DevSettings.model_fields:
            if name not in saved:
                continue
            try:  # strict, so "yes" is not read as a bool; a bad field keeps its default
                DevSettings.model_validate({name: saved[name]}, strict=True)
            except ValidationError:
                continue
            good[name] = saved[name]
        return DevSettings(**good)

    def update(self, patch: DevSettingsPatch) -> DevSettings:
        with self._lock:
            data = self.get().model_dump()
            changes = patch.model_dump(exclude_unset=True, exclude={"reset_system_prompt"})
            data.update({k: v for k, v in changes.items() if v is not None})
            if patch.reset_system_prompt:
                data["agent_system_prompt"] = None
            merged = DevSettings(**data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(merged.model_dump(), indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return merged
