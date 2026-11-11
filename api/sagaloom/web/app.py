import asyncio
import hmac
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.store.base import BaseStore
from pydantic import ValidationError

from sagaloom.auth import ClerkDirectory, ClerkVerifier, ProfileDirectory, TokenVerifier
from sagaloom.config import Settings, load_env_files
from sagaloom.llm import install_warning_filters
from sagaloom.locks import KeyedLocks
from sagaloom.model_settings import ModelSettings, validate_role_models
from sagaloom.promptlog import PromptLog
from sagaloom.seed import ensure_first_run
from sagaloom.settings_store import DevSettingsStore
from sagaloom.store.threads import ThreadRegistry
from sagaloom.store.users import UserRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.access import UnconfiguredVerifier, current_user
from sagaloom.web.limits import BodyLimitMiddleware, RateLimitMiddleware
from sagaloom.web.routes import router
from sagaloom.wiki.client import WikiClient

log = logging.getLogger(__name__)

# api/sagaloom/web/app.py -> repo root
SEED_DIR = Path(__file__).resolve().parents[3] / "seed" / "velmar"


@dataclass
class AppDeps:
    """Everything the routes use. Tests pass fakes; `create_app` fills the rest from `data_dir`
    (cheap file-backed registries now, Chroma and the graph at startup)."""

    store: Any = None
    worlds: WorldRegistry | None = None
    threads: ThreadRegistry | None = None
    graph: Any = None
    settings: Settings | None = None
    promptlog: PromptLog | None = None
    model_settings: ModelSettings | None = None
    dev_settings: DevSettingsStore | None = None
    wiki: WikiClient | None = None  # the shared MediaWiki client (R11.4.8)
    memory: BaseStore | None = None  # long-term author preferences (R10.2)
    seed_dir: Path | None = SEED_DIR
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)  # one running turn per thread
    # One preferences writer per world, shared by the graph's `remember` and the memory routes.
    memory_locks: KeyedLocks = field(default_factory=KeyedLocks)
    # role -> chat model, the same factory the graph uses (the import extractor runs on it).
    model_for: Callable[[str], Any] | None = None
    # Running turns, shielded from client disconnects; cancelled at shutdown.
    tasks: set[asyncio.Task] = field(default_factory=set)
    users: UserRegistry | None = None
    verifier: TokenVerifier | None = None  # Clerk session tokens -> claims
    directory: ProfileDirectory | None = None  # Clerk profiles; built at startup from the secret key
    user_locks: KeyedLocks = field(default_factory=KeyedLocks)  # one account write per user


# Roles that run on another role's model choice; not switchable on their own.
_ALIAS = {"router": "guard"}


def make_model_for(settings: Settings, model_settings: ModelSettings, factory=None):
    """role -> chat model. The current mapping is read on every call and one model is built per
    (role, model id), so a Studio switch (R11.G10) applies from the next turn."""
    if factory is None:
        from sagaloom.llm import make_chat_model

        providers = {m.id: m.provider for m in settings.allowed_models}

        def factory(role: str, model: str):
            # Pinned to the provider that serves this model, with no fallbacks (R11.G7, R22).
            return make_chat_model(settings, model=model, provider=providers.get(model))

    built: dict[tuple[str, str], Any] = {}

    def model_for(role: str):
        # The router uses the guard's current model but keeps its own role (and cache entry), so
        # its prompt records say `router` (spec 3.4).
        key = (role, model_settings.get_model_settings()[_ALIAS.get(role, role)])
        if key not in built:
            m = factory(*key)
            try:  # the prompt log reads the role from the model's metadata
                m.metadata = {**(getattr(m, "metadata", None) or {}), "role": role}
            except Exception:
                pass
            built[key] = m
        return built[key]

    return model_for


@asynccontextmanager
async def _open_runtime(app: FastAPI):
    """Builds Chroma and the graph (unless supplied), then seeds Velmar on first run."""
    deps: AppDeps = app.state.deps
    settings: Settings = app.state.settings
    install_warning_filters()
    async with AsyncExitStack() as stack:
        if deps.store is None:
            import chromadb

            from sagaloom.llm import make_embeddings
            from sagaloom.store.canon import CanonStore

            client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
            deps.store = CanonStore(client, make_embeddings(settings))
        if deps.wiki is None:
            deps.wiki = WikiClient(Path(settings.data_dir) / "cache" / "wiki")
        if deps.graph is None:
            from sagaloom.graph.build import build_graph, sqlite_checkpointer

            saver = await stack.enter_async_context(sqlite_checkpointer(settings))
            if deps.memory is None:
                # Same exit stack and event loop as the checkpointer (#30).
                from langgraph.store.sqlite.aio import AsyncSqliteStore

                deps.memory = await stack.enter_async_context(
                    AsyncSqliteStore.from_conn_string(str(Path(settings.data_dir) / "store.sqlite"))
                )
                await deps.memory.setup()
            deps.model_for = make_model_for(settings, deps.model_settings)
            deps.graph = build_graph(
                store=deps.store,
                model_for=deps.model_for,
                checkpointer=saver,
                dev=deps.dev_settings.get,
                wiki=deps.wiki,
                memory_store=deps.memory,
                memory_locks=deps.memory_locks,
            )
        if isinstance(deps.verifier, UnconfiguredVerifier):
            log.error("CLERK_ISSUER is not set: every sign-in will be rejected (set it in .env)")
        if deps.directory is None and settings.clerk_secret_key is not None:
            http = await stack.enter_async_context(httpx.AsyncClient(timeout=10))
            deps.directory = ClerkDirectory(settings.clerk_secret_key.get_secret_value(), http=http)
            stack.callback(setattr, deps, "directory", None)  # a restart opens a fresh client
        if deps.seed_dir is not None:
            await asyncio.to_thread(ensure_first_run, deps.store, deps.worlds, deps.seed_dir)
        try:
            yield
        finally:
            await _cancel_turns(deps.tasks)  # while the checkpointer is still open
            await deps.wiki.aclose()  # the shared HTTP client; reopened lazily on next use


async def _cancel_turns(tasks: set[asyncio.Task], timeout: float = 5.0) -> None:
    """Cancel the running turns and wait up to `timeout` for them; one that ignores the
    cancellation is logged and left behind rather than blocking shutdown."""
    pending = list(tasks)
    for t in pending:
        t.cancel()
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=timeout)
    if still_running:
        log.warning("%d turn(s) still running after %.1fs at shutdown", len(still_running), timeout)


def make_require_secret(secret: str):
    def require_secret(x_sagaloom_secret: str | None = Header(default=None)) -> None:
        supplied = x_sagaloom_secret or ""
        if not hmac.compare_digest(supplied.encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="unauthorised")

    return require_secret


def create_app(
    settings: Settings,
    deps: AppDeps | None = None,
    *,
    max_body_bytes: int = 1_000_000,
    rate_limits: dict[str, Any] | None = None,
) -> FastAPI:
    validate_role_models(settings)
    app = FastAPI(title="Sagaloom", lifespan=_open_runtime)
    data = Path(settings.data_dir)
    deps = deps or AppDeps()
    deps.settings = deps.settings or settings
    deps.worlds = deps.worlds or WorldRegistry(data / "worlds.json")
    deps.threads = deps.threads or ThreadRegistry(data / "threads.sqlite")
    deps.promptlog = deps.promptlog or PromptLog(data / "prompts.sqlite")
    deps.model_settings = deps.model_settings or ModelSettings(data / "model_settings.json", settings)
    deps.dev_settings = deps.dev_settings or DevSettingsStore(data / "settings.json")
    deps.users = deps.users or UserRegistry(data / "users.sqlite")
    if deps.verifier is None:
        deps.verifier = (
            ClerkVerifier(settings.clerk_issuer, settings.web_origin)
            if settings.clerk_issuer
            else UnconfiguredVerifier()
        )
    app.state.settings = settings
    app.state.deps = deps

    # add_middleware puts the newest outermost: CORS wraps the limiters, so their 413/429
    # responses still carry CORS headers, and the rate limit counts requests the body cap rejects.
    app.add_middleware(BodyLimitMiddleware, max_bytes=max_body_bytes)
    app.add_middleware(
        RateLimitMiddleware, **{"trusted_proxies": frozenset(settings.trusted_proxies), **(rate_limits or {})}
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # The shared secret guards every /api route; `authed` adds the signed-in user. Routers are
    # copied when included, so `authed` is filled before it goes into `protected`. A secret-only
    # route goes straight into `protected`.
    protected = APIRouter(
        prefix="/api", dependencies=[Depends(make_require_secret(settings.api_shared_secret.get_secret_value()))]
    )
    authed = APIRouter(dependencies=[Depends(current_user)])
    authed.include_router(router)
    protected.include_router(authed)
    app.include_router(protected)
    return app


def _with_env_export(app: FastAPI) -> FastAPI:
    """Export the env files at server startup, not at import: the unit tests import this module
    and must not pick up the developer's real environment (for example LangSmith tracing)."""
    runtime = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(a: FastAPI):
        load_env_files()
        async with runtime(a) as state:
            yield state

    app.router.lifespan_context = lifespan
    return app


def _build_default_app() -> FastAPI:
    try:
        return _with_env_export(create_app(Settings()))
    except (ValidationError, ValueError) as exc:  # ValidationError is a ValueError: test it first
        if isinstance(exc, ValidationError):
            missing = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
            message = f"Sagaloom API is misconfigured; set in api/.env or the environment: {missing}"
        else:
            message = f"Sagaloom API is misconfigured: {exc}"

        @asynccontextmanager
        async def fail(_app: FastAPI):
            raise RuntimeError(message)
            yield

        return FastAPI(lifespan=fail)


app = _build_default_app()
