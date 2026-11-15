"""Per-role model choice (R11.G10) and each role's fallback model (R11.G11): persisted to
`data/model_settings.json` and read on every model lookup, so a switch applies from the next turn.

The file holds the role mapping at the top level (`{"agent": ..., ...}`) and the fallbacks under
`"fallbacks"` (`{"agent": "<id>" | "", ...}`; "" means none for that role)."""

import json
import threading
from pathlib import Path
from typing import Literal, get_args

from sagaloom.config import Settings

Role = Literal["agent", "judge", "extractor", "guard"]
ROLES: tuple[str, ...] = get_args(Role)


def default_models(settings: Settings) -> dict[str, str]:
    """role -> model id from the environment (or the built-in default)."""
    s = settings
    return {
        "agent": s.chat_model,
        "judge": s.judge_model,
        "extractor": s.extractor_model,
        "guard": s.guard_model,
    }


_ENV_VAR = {"agent": "CHAT_MODEL", "judge": "JUDGE_MODEL", "extractor": "EXTRACTOR_MODEL", "guard": "GUARD_MODEL"}


def validate_role_models(settings: Settings) -> None:
    """Fail fast at startup when a default role model from the environment is not on the
    allowlist, instead of failing at call time with a raw API error (R11.G10)."""
    allowed = {m.id for m in settings.allowed_models}
    defaults = default_models(settings)
    bad = [f"{_ENV_VAR[role]}={model}" for role, model in defaults.items() if model not in allowed]
    if settings.fallback_model and settings.fallback_model not in allowed:
        bad.append(f"FALLBACK_MODEL={settings.fallback_model}")
    if bad:
        raise ValueError(
            f"model not in sagaloom/allowed_models.json: {', '.join(bad)}. "
            "Pick a listed model id."
        )


class ModelSettings:
    def __init__(self, path: Path, settings: Settings):
        self.path = Path(path)
        self.settings = settings
        self._lock = threading.Lock()

    def _defaults(self) -> dict[str, str]:
        return default_models(self.settings)

    def _allowed(self) -> set[str]:
        return {m.id for m in self.settings.allowed_models}

    def _saved(self) -> dict:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return saved if isinstance(saved, dict) else {}

    def _write(self, saved: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get_fallbacks(self) -> dict[str, str | None]:
        """role -> fallback model id, or None for no fallback. FALLBACK_MODEL (the built-in
        default) unless the admin chose another or none for that role; an id no longer on the
        allowlist counts as the default."""
        default = self.settings.fallback_model or None
        mapping: dict[str, str | None] = {role: default for role in ROLES}
        saved = self._saved().get("fallbacks")
        if isinstance(saved, dict):
            allowed = self._allowed()
            for role in ROLES:
                value = saved.get(role)
                if value == "":
                    mapping[role] = None
                elif isinstance(value, str) and value in allowed:
                    mapping[role] = value
        return mapping

    def set_fallback(self, role: Role, model: str | None) -> None:
        """Choose a role's fallback; None (or "") for none."""
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        if model and model not in self._allowed():
            raise ValueError(f"model is not on the allowlist: {model}")
        with self._lock:
            saved = self._saved()
            fallbacks = saved.get("fallbacks") if isinstance(saved.get("fallbacks"), dict) else {}
            saved["fallbacks"] = {**fallbacks, role: model or ""}
            self._write(saved)

    def get_model_settings(self) -> dict[str, str]:
        mapping = self._defaults()
        saved = self._saved()
        if saved:
            allowed = self._allowed()
            for role in ROLES:
                if isinstance(saved.get(role), str) and saved[role] in allowed:
                    mapping[role] = saved[role]
        return mapping

    def set_model(self, role: Role, model: str) -> None:
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        if model not in self._allowed():
            raise ValueError(f"model is not on the allowlist: {model}")
        with self._lock:
            saved = self._saved()
            self._write({**saved, **self.get_model_settings(), role: model})
