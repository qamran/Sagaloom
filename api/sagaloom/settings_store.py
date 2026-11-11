"""Developer settings (R12.4): persisted to `data/settings.json` and read on every call, so a
change applies from the next turn. Judge, extractor and guard temperatures are not editable."""

import json
import logging
import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from sagaloom.tools.specs import CORE_TOOLS, TOOL_SPECS

log = logging.getLogger(__name__)

ALL_TOOLS = frozenset(spec["name"] for spec in TOOL_SPECS)


def _known_tools(names: list[str] | None) -> list[str] | None:
    unknown = sorted(set(names or []) - ALL_TOOLS)
    if unknown:
        raise ValueError(f"unknown tool: {', '.join(unknown)}")
    return names


class DevSettings(BaseModel):
    agent_temperature: float = Field(default=0.0, ge=0, le=2)
    agent_max_tokens: int | None = Field(default=None, ge=256, le=16000)
    agent_system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    guard_enabled: bool = True
    # None means every tool. Core tools are always on, whatever this lists (R11.G3).
    enabled_tools: list[str] | None = None
    # Each non-admin account's AI spend per calendar month (UTC), in US$ (M5 spec §5.5a).
    monthly_budget_usd: float = Field(default=1.0, ge=0, le=1000)

    _check_tools = field_validator("enabled_tools")(_known_tools)


def enabled_tool_names(d: DevSettings) -> set[str]:
    if d.enabled_tools is None:
        return set(ALL_TOOLS)
    return set(d.enabled_tools) | CORE_TOOLS


class DevSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_temperature: float | None = Field(default=None, ge=0, le=2)
    agent_max_tokens: int | None = Field(default=None, ge=256, le=16000)
    agent_system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    guard_enabled: bool | None = None
    enabled_tools: list[str] | None = None
    # Not nullable; only a field the request sets is written (`update` reads `model_fields_set`).
    monthly_budget_usd: float = Field(default=1.0, ge=0, le=1000)
    reset_system_prompt: bool = False

    _check_tools = field_validator("enabled_tools")(_known_tools)

    @model_validator(mode="after")
    def _no_null_for_required(self):
        for name in ("agent_temperature", "guard_enabled"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class DevSettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._warned_tools: object = None  # the last raw enabled_tools value warned about

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
                if name == "enabled_tools" and saved[name] != self._warned_tools:
                    self._warned_tools = saved[name]
                    log.warning("settings.json lists unknown tools; every tool stays enabled")
                continue
            good[name] = saved[name]
        return DevSettings(**good)

    def update(self, patch: DevSettingsPatch) -> DevSettings:
        with self._lock:
            data = self.get().model_dump()
            for name in patch.model_fields_set - {"reset_system_prompt"}:
                data[name] = getattr(patch, name)  # an explicit null clears a nullable field
            if patch.reset_system_prompt:
                data["agent_system_prompt"] = None
            merged = DevSettings(**data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(merged.model_dump(), indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return merged
