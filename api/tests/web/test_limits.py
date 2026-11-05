"""Body cap and per-client rate limit (R13.4, R16.4). Pure ASGI, so tests drive a tiny app."""

import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel
from httpx import ASGITransport, AsyncClient

from sagaloom.web.limits import BodyLimitMiddleware, RateLimitMiddleware


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def build(**kw) -> FastAPI:
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    class Msg(BaseModel):
        content: str

    @app.post("/model")
    async def model(m: Msg):
        return {"n": len(m.content)}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/worlds")
    def worlds():
        return []

    @app.post("/api/threads/{tid}/messages")
    def messages(tid: str):
        return {"ok": True}

    @app.post("/api/threads/{tid}/decisions")
    def decisions(tid: str):
        return {"ok": True}

    if "max_bytes" in kw:
        app.add_middleware(BodyLimitMiddleware, max_bytes=kw.pop("max_bytes"))
    if kw:
        app.add_middleware(RateLimitMiddleware, **kw)
    return app


def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_body_over_cap_is_413():
    async with client(build(max_bytes=100)) as c:
        r = await c.post("/echo", content=b"x" * 101)
        assert r.status_code == 413 and r.json() == {"detail": "request too large"}
        assert (await c.post("/echo", content=b"x" * 100)).status_code == 200


async def test_streamed_body_over_cap_is_413():
    async def chunks():
        for _ in range(5):
            yield b"x" * 40

    async with client(build(max_bytes=100)) as c:
        r = await c.post("/echo", content=chunks())  # no Content-Length: chunked
        assert r.status_code == 413 and r.json() == {"detail": "request too large"}


async def test_turn_limit_per_client():
    clock = Clock()
    async with client(build(turn_limit=2, clock=clock)) as c:
        one = {"X-Forwarded-For": "1.1.1.1"}
        for _ in range(2):
            assert (await c.post("/api/threads/x/messages", headers=one)).status_code == 200
        r = await c.post("/api/threads/x/decisions", headers=one)
        assert r.status_code == 429 and r.json() == {"detail": "rate limited"}
        assert int(r.headers["Retry-After"]) >= 1
        other = await c.post("/api/threads/x/messages", headers={"X-Forwarded-For": "2.2.2.2"})
        assert other.status_code == 200
        clock.now += 61
        assert (await c.post("/api/threads/x/messages", headers=one)).status_code == 200


async def test_first_forwarded_hop_is_the_key():
    async with client(build(turn_limit=1, clock=Clock())) as c:
        assert (await c.post("/api/threads/x/messages", headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9"})).status_code == 200
        assert (await c.post("/api/threads/x/messages", headers={"X-Forwarded-For": "1.1.1.1, 8.8.8.8"})).status_code == 429


async def test_health_exempt():
    async with client(build(turn_limit=1, total_limit=1, clock=Clock())) as c:
        for _ in range(5):
            assert (await c.get("/api/health")).status_code == 200


async def test_total_limit_counts_gets():
    async with client(build(total_limit=3, clock=Clock())) as c:
        for _ in range(3):
            assert (await c.get("/api/worlds")).status_code == 200
        r = await c.get("/api/worlds")
        assert r.status_code == 429 and "Retry-After" in r.headers


async def test_limit_response_carries_cors_headers():
    from sagaloom.config import Settings
    from sagaloom.web.app import create_app

    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s", web_origin="http://web.test")
    app = create_app(settings, rate_limits={"total_limit": 1}, max_body_bytes=50)
    async with client(app) as c:
        h = {"Origin": "http://web.test", "X-Sagaloom-Secret": "s"}
        big = await c.post("/api/worlds", content=b"x" * 60, headers=h)
        assert big.status_code == 413 and big.headers["access-control-allow-origin"] == "http://web.test"
        await c.get("/api/worlds", headers=h)
        limited = await c.get("/api/worlds", headers=h)
        assert limited.status_code == 429 and limited.headers["access-control-allow-origin"] == "http://web.test"


async def test_streamed_over_cap_pydantic_body_is_413_not_400():
    async def chunks():
        yield b'{"content": "'
        for _ in range(5):
            yield b"x" * 40
        yield b'"}'

    async with client(build(max_bytes=100)) as c:
        r = await c.post("/model", content=chunks(), headers={"Content-Type": "application/json"})
        assert r.status_code == 413 and r.json() == {"detail": "request too large"}


async def test_idle_keys_are_swept_once_per_window():
    clock = Clock()
    app = build(total_limit=5, clock=clock)
    async with client(app) as c:
        for i in range(3):
            await c.get("/api/worlds", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        limiter = app.middleware_stack  # built lazily on first request
        while not isinstance(limiter, RateLimitMiddleware):
            limiter = limiter.app
        assert len(limiter._totals) == 3
        clock.now += 61
        await c.get("/api/worlds", headers={"X-Forwarded-For": "10.0.1.1"})
        assert list(limiter._totals) == ["10.0.1.1"]
