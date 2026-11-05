"""Data for the Studio page (R20.4, R20.5, R20.7): the feature map, providers and usage.
Nothing here ever returns a key value, only whether one is set."""

import os
from typing import Any, Literal

from pydantic import BaseModel

from sagaloom.config import Settings
from sagaloom.tools.specs import TOOL_SPECS

EMBED_PRICE_IN = 0.02  # USD per 1M tokens, openai/text-embedding-3-small
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_NOTICE = (
    "Free-tier Gemini prompts may be used by Google to improve its products (R11.G9). "
    "Sagaloom never sends a request to Gemini: this entry only shows that a key is configured."
)


class FeatureCard(BaseModel):
    id: str
    title: str
    brief_ref: str
    req_ids: list[str]
    status: Literal["live", "configured", "off"]
    detail: str
    try_href: str | None = None


class ProviderModel(BaseModel):
    id: str
    role: str
    price_in: float | None = None
    price_out: float | None = None


class ProviderStatus(BaseModel):
    name: str
    key_set: bool
    role: str
    models: list[ProviderModel]
    notice: str | None = None


def gemini_key_set(settings: Settings) -> bool:
    """A non-empty key; the value itself is never used."""
    key = settings.gemini_api_key
    return key is not None and bool(key.get_secret_value())


def langsmith_live() -> bool:
    """R20.5: live only when tracing is on and a key is present (values are never returned)."""
    return os.environ.get("LANGSMITH_TRACING") == "true" and bool(os.environ.get("LANGSMITH_API_KEY"))


def build_feature_map(settings: Settings, deps: Any) -> list[FeatureCard]:
    threads = None
    if getattr(deps, "threads", None) is not None:
        try:
            threads = len(deps.threads.list())
        except Exception:
            pass
    cost = None
    if getattr(deps, "promptlog", None) is not None:
        try:
            cost = deps.promptlog.total_usage().cost_usd
        except Exception:
            pass
    guard_on = True
    if getattr(deps, "dev_settings", None) is not None:
        try:
            guard_on = deps.dev_settings.get().guard_enabled
        except Exception:
            pass
    project = os.environ.get("LANGSMITH_PROJECT")
    ls_live = langsmith_live()
    gemini_set = gemini_key_set(settings)
    prompt = "/chat?prompt="
    return [
        FeatureCard(
            id="agent_purpose",
            title="Agent purpose",
            brief_ref="Brief req 1",
            req_ids=["R1.1", "R11.1"],
            status="live",
            detail="A continuity editor for story worlds: it answers from canon and drafts changes that wait for your approval.",
            try_href=prompt + "What do we know about Velmar?",
        ),
        FeatureCard(
            id="agentic_rag",
            title="Agentic RAG",
            brief_ref="Hard 1",
            req_ids=["R7", "R11.1", "R11.3"],
            status="live",
            detail="The agent decides when to search canon, and answers cite entry IDs.",
            try_href=prompt + "How many moons does Velmar have?",
        ),
        FeatureCard(
            id="human_in_the_loop",
            title="Human-in-the-loop",
            brief_ref="Sprint topic",
            req_ids=["R5", "R18.2", "R18.3", "R18.4"],
            status="live",
            detail="Every write pauses at interrupt() until you approve, edit, reject or save it as myth.",
            try_href=prompt + "Add a place called Ostra, a port town with a deep harbour.",
        ),
        FeatureCard(
            id="memory",
            title="Memory",
            brief_ref="Medium 2",
            req_ids=["R10.1", "R18.6", "R18.7"],
            status="live",
            detail="Short-term memory: a SQLite checkpointer"
            + (f", {threads} threads" if threads is not None else "")
            + ". Survives refresh and restart.",
            try_href="/chat",
        ),
        FeatureCard(
            id="token_cost",
            title="Token usage and cost",
            brief_ref="Medium 1",
            req_ids=["R14.1", "R14.2"],
            status="live",
            detail="Per turn and per session, from OpenRouter's reported usage."
            + (f" Session: ${cost:.4f}." if cost is not None else ""),
            try_href="#usage",
        ),
        FeatureCard(
            id="langsmith",
            title="LangSmith tracing",
            brief_ref="Hard 2",
            req_ids=["R15.1"],
            status="live" if ls_live else "off",
            detail=(
                "Runs are grouped by thread_id" + (f' in project "{project}".' if project else ".")
                if ls_live
                else "Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to turn tracing on."
            ),
            try_href="/chat" if ls_live else None,
        ),
        FeatureCard(
            id="multi_provider",
            title="Multi-model, multi-provider",
            brief_ref="Medium 7",
            req_ids=["R11.G8", "R11.G9", "R11.G10"],
            status="configured" if gemini_set else "off",
            detail=(
                "OpenRouter models per role. A Gemini key is present, demo only: Sagaloom never calls it."
                if gemini_set
                else "OpenRouter models per role. The Gemini provider is not configured (the full feature is M2)."
            ),
            try_href="#models",
        ),
        FeatureCard(
            id="security_guard",
            title="Security guard",
            brief_ref="Medium 8",
            req_ids=["R13.1", "R13.2", "R13.3", "R12.4", "R20.1"],
            status="live" if guard_on else "off",
            detail=(
                "The input guard checks each message before the agent sees it. Retrieved and imported "
                "text is wrapped as untrusted data; keys never leave the server."
                if guard_on
                else "The input guard is off (turned off in Studio), so messages go straight to the agent. "
                "Retrieved and imported text is still wrapped as untrusted data."
            ),
            try_href="#guardrails" if not guard_on else prompt + "Which entries mention Ister?",
        ),
        FeatureCard(
            id="tools",
            title="Tools and plugins",
            brief_ref="Medium 6",
            req_ids=["R11.G1", "R11.G3"],
            status="live",
            detail=(
                f"{len(TOOL_SPECS)} tools. The core tools are always on; turn the others on or off in Studio."
            ),
            try_href="#tools",
        ),
        FeatureCard(
            id="external_tools",
            title="External data tools",
            brief_ref="Medium 3, Hard 5",
            req_ids=["R11.4", "R11.6"],
            status="live",
            detail="Wikipedia reference tool; fan-wiki import arrives in Wave 6.",
            try_href=prompt
            + "What did Byzantine trade routes look like? I want Velmar's harbour to feel like that.",
        ),
    ]


def providers_status(settings: Settings, mapping: dict[str, str] | None = None) -> list[ProviderStatus]:
    """`mapping` is the current role -> model choice; without it the configured defaults show."""
    mapping = mapping or {}
    by_id = {m.id: m for m in settings.allowed_models}

    def model(role: str, id: str) -> ProviderModel:
        m = by_id.get(id)
        return ProviderModel(
            id=id, role=role, price_in=m.price_in if m else None, price_out=m.price_out if m else None
        )

    return [
        ProviderStatus(
            name="OpenRouter",
            key_set=bool(settings.openrouter_api_key.get_secret_value()),
            role="all real calls, provider pinned",
            models=[
                model("agent", mapping.get("agent", settings.chat_model)),
                model("judge", mapping.get("judge", settings.judge_model)),
                model("extractor", mapping.get("extractor", settings.extractor_model)),
                ProviderModel(id=settings.embed_model, role="embeddings", price_in=EMBED_PRICE_IN, price_out=0.0),
            ],
        ),
        ProviderStatus(
            name="Gemini",
            key_set=gemini_key_set(settings),
            role="demo only, not used for real calls",
            models=[ProviderModel(id=GEMINI_MODEL, role="demo")],
            notice=GEMINI_NOTICE,
        ),
    ]
