import hmac
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from sagaloom.config import Settings


@dataclass
class AppDeps:
    """Dependencies wired in by later tasks."""


def make_require_secret(secret: str):
    def require_secret(x_sagaloom_secret: str | None = Header(default=None)) -> None:
        supplied = x_sagaloom_secret or ""
        if not hmac.compare_digest(supplied.encode(), secret.encode()):
            raise HTTPException(status_code=401, detail="unauthorised")

    return require_secret


def create_app(settings: Settings, deps: AppDeps | None = None) -> FastAPI:
    app = FastAPI(title="Sagaloom")
    app.state.settings = settings
    app.state.deps = deps or AppDeps()

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
        prefix="/api", dependencies=[Depends(make_require_secret(settings.api_shared_secret))]
    )

    @protected.get("/worlds")
    def list_worlds() -> list:
        return []

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
