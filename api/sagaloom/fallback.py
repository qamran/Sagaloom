"""A named fallback model per role (R11.G11).

Every call is still pinned to one provider with OpenRouter's own fallbacks off (R11.G7), so a
call never silently runs on another model. This is a separate, visible step on top: when a role's
model is withdrawn (`gone`), refused for this key (`blocked`) or its provider is failing (`down`),
after the client's own retries, the same request goes once to the role's named fallback model.

- The primary's failed call stays in the prompt log with its cause, and the fallback's call is a
  run of its own whose record names the model it replaced and why (`fallback_for`,
  `fallback_reason`). Under the hood, the turn's cost line and Studio show it.
- Only those three kinds fall back. On `no_credit`, `bad_key`, `rate_limited`, `rejected`,
  `timeout` and `network` another model would fail the same way or hide a bug, so the error
  surfaces as before.
- A streamed reply that already sent text is not replayed on another model (the author would see
  it twice): `OpenRouterChat` marks such an error with `PARTIAL_OUTPUT`.
- When the fallback fails too, the primary's error is raised with the fallback's failure attached
  (`FALLBACK_FAILURE`), so the message names both models; the guard and the judge still fail
  closed.
"""

import logging
from typing import Any

from langchain_core.runnables.config import ensure_config

from sagaloom.model_errors import FALLBACK_FAILURE, classify, failure_line

log = logging.getLogger(__name__)

FALLBACK_KINDS = frozenset({"gone", "blocked", "down"})
# Set on an exception by OpenRouterChat when a streamed reply had already sent text.
PARTIAL_OUTPUT = "sagaloom_partial_output"


def should_fall_back(exc: BaseException) -> bool:
    """Whether a failed call may be retried on the fallback model."""
    if getattr(exc, PARTIAL_OUTPUT, False):
        return False
    failure = classify(exc)
    return failure is not None and failure.kind in FALLBACK_KINDS


class FallbackModel:
    """A role's model with its fallback. Builds the same chain on both (`bind_tools`, `bind`,
    `with_structured_output`), so whatever a node does to its model, the fallback answers the
    same request. Anything else is read from the primary (its model name, for messages)."""

    def __init__(self, primary: Any, fallback: Any, *, primary_id: str, fallback_id: str):
        self.primary = primary
        self.fallback = fallback
        self.primary_id = primary_id
        self.fallback_id = fallback_id

    def _both(self, op: str, *args: Any, **kwargs: Any) -> "FallbackModel":
        return FallbackModel(
            getattr(self.primary, op)(*args, **kwargs),
            getattr(self.fallback, op)(*args, **kwargs),
            primary_id=self.primary_id,
            fallback_id=self.fallback_id,
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackModel":
        return self._both("bind_tools", tools, **kwargs)

    def bind(self, **kwargs: Any) -> "FallbackModel":
        return self._both("bind", **kwargs)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> "FallbackModel":
        return self._both("with_structured_output", schema, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.primary, name)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return await self.primary.ainvoke(input, config, **kwargs)
        except Exception as exc:
            if not should_fall_back(exc):
                raise
            reason = failure_line(exc)
            log.warning("%s failed (%s); trying the fallback model %s", self.primary_id, reason, self.fallback_id)
            # The call's config (or the graph's, from context) with the note added to its metadata,
            # so the fallback's record keeps the thread, the role and every other tag.
            cfg = ensure_config(config)
            cfg["metadata"] = {**(cfg.get("metadata") or {}), "fallback_for": self.primary_id, "fallback_reason": reason}
            try:
                return await self.fallback.ainvoke(input, cfg, **kwargs)
            except Exception as second:
                setattr(exc, FALLBACK_FAILURE, (self.fallback_id, failure_line(second)))
                raise exc


