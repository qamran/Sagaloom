import asyncio
import hmac
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from sagaloom.config import Settings
from sagaloom.promptlog import PromptLog
from sagaloom.seed import ensure_first_run
from sagaloom.store.threads import ThreadRegistry
from sagaloom.store.worlds import WorldRegistry
from sagaloom.web.routes import router

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
    seed_dir: Path | None = SEED_DIR


def make_model_for(settings: Settings):
    """role -> chat model, from the configured role models (Task 12 adds persisted switching)."""
    from sagaloom.llm import make_chat_model

    models = {
        "agent": settings.chat_model,
        "judge": settings.judge_model,
        "extractor": settings.extractor_model,
        "guard": settings.guard_model,
    }
    built = {role: make_chat_model(settings, model=m) for role, m in models.items()}
    return lambda role: built[role]


@asynccontextmanager
async def _open_runtime(app: FastAPI):
    """Builds Chroma and the graph (unless supplied), then seeds Velmar on first run."""
    deps: AppDeps = app.state.deps
    settings: Settings = app.state.settings
    async with AsyncExitStack() as stack:
        if deps.store is None:
            import chromadb

            from sagaloom.llm import make_embeddings
            from sagaloom.store.canon import CanonStore

            client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
            deps.store = CanonStore(client, make_embeddings(settings))
        if deps.graph is None:
            from sagaloom.graph.build import build_graph, sqlite_checkpointer

            saver = await stack.enter_async_context(sqlite_checkpointer(settings))
            deps.graph = build_graph(
                store=deps.store,
                model_for=make_model_for(settings),
                checkpointer=saver,
                settings=settings,
            )
        if deps.seed_dir is not None:
            await asyncio.to_thread(ensure_first_run, deps.store, deps.worlds, deps.seed_dir)
        yield


def make_require_secret(secret: str):
    def require_secret(x_sagaloom_secret: str | None = Header(default=None)) -> None:
        supplied = x_sagaloom_secret or ""
        if not hmac.compare_digest(supplied.encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="unauthorised")

    return require_secret


def create_app(settings: Settings, deps: AppDeps | None = None) -> FastAPI:
    app = FastAPI(title="Sagaloom", lifespan=_open_runtime)
    data = Path(settings.data_dir)
    deps = deps or AppDeps()
    deps.settings = deps.settings or settings
    deps.worlds = deps.worlds or WorldRegistry(data / "worlds.json")
    deps.threads = deps.threads or ThreadRegistry(data / "threads.sqlite")
    deps.promptlog = deps.promptlog or PromptLog(data / "prompts.sqlite")
    app.state.settings = settings
    app.state.deps = deps

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    protected = APIRouter(
        prefix="/api", dependencies=[Depends(make_require_secret(settings.api_shared_secret.get_secret_value()))]
    )

    protected.include_router(router)
    app.include_router(protected)
    return app


def _build_default_app() -> FastAPI:
    try:
        return create_app(Settings())
    except ValidationError as exc:
        missing = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
        message = f"Sagaloom API is misconfigured; set in api/.env or the environment: {missing}"

        @asynccontextmanager
        async def fail(_app: FastAPI):
            raise RuntimeError(message)
            yield

        return FastAPI(lifespan=fail)


app = _build_default_app()
