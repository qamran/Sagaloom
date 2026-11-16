"""The Jev decision model as the router's engine (R6.6).

When `router_engine` is `"jev"`, one message's mode is chosen by TypeSafe's Jev decision model
(through OpenRouter) instead of an LLM. `classify_mode` asks one `Choice` question and returns the
mode with Jev's confidence. Every call, answered or failed, is recorded in the prompt log through
a custom event (`DECISION_EVENT`, read by `PromptLogHandler.on_custom_event`) as an unpriced call:
Jev's cost is never estimated.
"""

import json
import logging
import time
import uuid
import warnings
from typing import Any, get_args

from langchain_core._api import LangChainBetaWarning
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_typesafe import Choice, TypeSafeClassifier
from pydantic import BaseModel

from sagaloom.config import Settings
from sagaloom.graph.state import Mode
from sagaloom.model_errors import failure_line

logger = logging.getLogger(__name__)

DECISION_EVENT = "decision_call"
DECISION_TIMEOUT = 10.0  # seconds; no retry, the LLM decides instead
_MODES = frozenset(get_args(Mode))

# Worded from `router.ROUTER_PROMPT`'s mode descriptions.
ROUTER_QUESTION = Choice(
    instructions=(
        "The state is one message from an author to Sagaloom, a continuity editor for fictional "
        "worlds they invent. Which mode does the message need? Decide by what the author wants, "
        "not by the grammar of the sentence."
    ),
    criteria={
        "brainstorm": (
            "The author wants new ideas, options or suggestions that are not settled yet: names, "
            "plots, legends, conflicts, 'what could...', 'help me think up...', 'suggest...', "
            "'give me ideas...', 'I'm stuck...'. A question that asks to invent something is "
            "brainstorm."
        ),
        "query": (
            "The author wants to know what the world already says: questions about existing lore, "
            "'how many...', 'who is...', 'what do we know about...', 'which entries mention...', "
            "'is there anything in canon about...'."
        ),
        "edit": (
            "The author states a fact about the world or asks to add, change, rename or delete "
            "something in it: 'X has two moons now', 'add a place called...', 'update her entry', "
            "'delete the rumour...'. A plain statement about the world ('the harbour freezes every "
            "winter') is edit, even with no verb like 'add'."
        ),
    },
)


class JevDecision(BaseModel):
    mode: Mode
    confidence: float
    model: str


class DecisionFailed(Exception):
    """Jev answered, but not with a usable mode (no `mode` answer, or a label outside the modes)."""


def decision_base_url(openrouter_base_url: str) -> str:
    """OpenRouter's base URL for the classifier, which adds `/v1/systemone` itself."""
    url = openrouter_base_url.rstrip("/")
    return url[: -len("/v1")] if url.endswith("/v1") else url


def make_router_classifier(settings: Settings) -> TypeSafeClassifier:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", LangChainBetaWarning)  # the package marks itself beta
        return TypeSafeClassifier(
            model=settings.router_decision_model,
            api_key=settings.openrouter_api_key,
            base_url=decision_base_url(settings.openrouter_base_url),
            timeout=DECISION_TIMEOUT,
        )


async def classify_mode(
    classifier: Any, text: str, *, config: RunnableConfig | None = None
) -> JevDecision:
    """The mode Jev picks for `text`. Raises `DecisionFailed` for an unusable answer and lets the
    classifier's own errors through; either way the call is recorded first."""
    started = time.monotonic()
    response = None
    try:
        response = await classifier.ainvoke(
            {"state": text, "questions": {"mode": ROUTER_QUESTION}}, config=config
        )
        answer = response.choices.get("mode")
        if answer is None:
            raise DecisionFailed("Jev gave no mode answer")
        if answer.choice not in _MODES:
            raise DecisionFailed(f"Jev answered an unknown mode: {answer.choice[:40]!r}")
        decision = JevDecision(mode=answer.choice, confidence=answer.confidence, model=response.model)
    except Exception as exc:
        await _record(classifier, text, started, response=response, error=exc, config=config)
        raise
    await _record(classifier, text, started, response=response, decision=decision, config=config)
    return decision


async def _record(
    classifier: Any,
    text: str,
    started: float,
    *,
    response: Any = None,
    decision: JevDecision | None = None,
    error: BaseException | None = None,
    config: RunnableConfig | None,
) -> None:
    """Sends the call to the prompt log. With no handler or no parent run (the eval, unit
    tests) there is nowhere to send it: that is never an error."""
    model = getattr(response, "model", None) or str(getattr(classifier, "model", None) or "unknown")
    usage = getattr(response, "usage", None)
    out: dict[str, Any] = {
        "content": "",
        "tool_calls": [],
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": None,
        "priced": False,
        "latency_ms": int((time.monotonic() - started) * 1000),
    }
    if decision is not None:
        out["content"] = json.dumps(
            {"mode": decision.mode, "confidence": decision.confidence, "engine": "jev"}
        )
        out["prompt_tokens"] = (usage.input_tokens or 0) if usage else 0
        out["completion_tokens"] = (usage.output_tokens or 0) if usage else 0
    if error is not None:
        out["error"] = failure_line(error)
    payload = {
        "id": uuid.uuid4().hex,
        "role": "router",
        "provider": "openrouter",
        "model": model,
        "params": {"engine": "jev", "timeout": DECISION_TIMEOUT},
        "request": {
            "messages": [{"role": "user", "content": text}],
            "tools": [],
            "question": ROUTER_QUESTION.model_dump(mode="json"),
        },
        "response": out,
    }
    try:
        await adispatch_custom_event(DECISION_EVENT, payload, config=config)
    except Exception:
        logger.debug("Jev decision call not recorded", exc_info=True)
