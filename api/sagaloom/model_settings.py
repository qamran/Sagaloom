"""Per-role model choice (R11.G10): persisted to `data/model_settings.json` and read on every
model lookup, so a switch applies from the next turn."""

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

    def get_model_settings(self) -> dict[str, str]:
        mapping = self._defaults()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        if isinstance(saved, dict):
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
            mapping = self.get_model_settings()
            mapping[role] = model
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
            tmp.replace(self.path)
