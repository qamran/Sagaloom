"""Body cap and per-client rate limit (R13.4, R16.4). Pure ASGI, so tests drive a tiny app."""

import json

import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel
from httpx import ASGITransport, AsyncClient

from sagaloom.web.limits import TURN_PATH, BodyLimitMiddleware, RateLimitMiddleware

PEER = frozenset({"127.0.0.1"})  # httpx's ASGITransport reports the client as 127.0.0.1


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

    @app.post("/api/worlds/{wid}/imports")
    def imports(wid: str):
        return {"ok": True}

    if "max_bytes" in kw:
        app.add_middleware(BodyLimitMiddleware, max_bytes=kw.pop("max_bytes"))
    if kw:
        app.add_middleware(RateLimitMiddleware, **kw)
    return app


def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def limiter_of(app: FastAPI) -> RateLimitMiddleware:
    limiter = app.middleware_stack  # built lazily on first request
    while not isinstance(limiter, RateLimitMiddleware):
        limiter = limiter.app
    return limiter


def scope_from(peer: str | None, *xff: str) -> dict:
    return {
        "type": "http",
        "client": (peer, 5000) if peer else None,
        "headers": [(b"x-forwarded-for", v.encode()) for v in xff],
    }


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


async def test_malformed_content_length_still_capped_by_stream():
    # httpx will not send a malformed Content-Length, so drive the middleware with a raw scope.
    app = BodyLimitMiddleware(build(), max_bytes=100)
    chunks = [
        {"type": "http.request", "body": b"x" * 60, "more_body": True},
        {"type": "http.request", "body": b"x" * 60, "more_body": False},
    ]
    sent: list[dict] = []

    async def receive():
        return chunks.pop(0) if chunks else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/echo",
        "raw_path": b"/echo",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-length", b"abc")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    assert start["status"] == 413 and json.loads(body) == {"detail": "request too large"}


async def test_turn_limit_per_client():
    clock = Clock()
    async with client(build(turn_limit=2, clock=clock, trusted_proxies=PEER)) as c:
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


async def test_import_counts_as_a_turn():
    assert TURN_PATH.match("/api/worlds/w/imports")
    assert not TURN_PATH.match("/api/worlds/w/imports/x")
    assert not TURN_PATH.match("/api/worlds/w/entries")
    async with client(build(turn_limit=1, clock=Clock(), trusted_proxies=PEER)) as c:
        one = {"X-Forwarded-For": "1.1.1.1"}
        assert (await c.post("/api/worlds/w/imports", headers=one)).status_code == 200
        assert (await c.post("/api/threads/x/messages", headers=one)).status_code == 429


def test_rightmost_untrusted_hop_from_trusted_proxy():
    one = RateLimitMiddleware(None, trusted_proxies=frozenset({"127.0.0.1"}))
    assert one.client_key(scope_from("127.0.0.1", "1.1.1.1, 2.2.2.2")) == "2.2.2.2"
    both = RateLimitMiddleware(None, trusted_proxies=frozenset({"127.0.0.1", "10.0.0.1"}))
    assert both.client_key(scope_from("127.0.0.1", "1.1.1.1, 10.0.0.1")) == "1.1.1.1"
    # Repeated headers read as one comma-joined list, so the right-most hop is in the last one.
    assert one.client_key(scope_from("127.0.0.1", "2.2.2.2", "3.3.3.3")) == "3.3.3.3"
    # A trusted peer with no usable hop is keyed by its own address, never by an empty string.
    assert one.client_key(scope_from("127.0.0.1")) == "127.0.0.1"
    assert one.client_key(scope_from("127.0.0.1", " , ")) == "127.0.0.1"
    assert both.client_key(scope_from("127.0.0.1", "10.0.0.1")) == "127.0.0.1"


def test_xff_ignored_from_untrusted_peer():
    default = RateLimitMiddleware(None)  # TRUSTED_PROXIES empty: no peer is trusted
    other = RateLimitMiddleware(None, trusted_proxies=frozenset({"10.0.0.9"}))
    for limiter in (default, other):
        assert limiter.client_key(scope_from("8.8.8.8", "1.1.1.1")) == "8.8.8.8"
        assert limiter.client_key(scope_from("8.8.8.8", "1.1.1.1, 10.0.0.9")) == "8.8.8.8"
        assert limiter.client_key(scope_from(None, "1.1.1.1")) == "unknown"


async def test_untrusted_peer_is_keyed_by_socket_whatever_the_header_says():
    from sagaloom.config import Settings
    from sagaloom.web.app import create_app

    # The default trusts no proxy, so rotating X-Forwarded-For buys no fresh window.
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s")
    assert settings.trusted_proxies == []
    app = create_app(settings, rate_limits={"total_limit": 2})
    async with client(app) as c:
        h = {"X-Sagaloom-Secret": "s"}
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "1.1.1.1"})).status_code == 200
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "2.2.2.2"})).status_code == 200
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "3.3.3.3"})).status_code == 429
        assert list(limiter_of(app)._totals) == ["127.0.0.1"]


async def test_trusted_proxies_setting_reaches_the_limiter(monkeypatch):
    from sagaloom.config import Settings
    from sagaloom.web.app import create_app

    monkeypatch.setenv("TRUSTED_PROXIES", '["127.0.0.1"]')
    settings = Settings(_env_file=None, openrouter_api_key="k", api_shared_secret="s")
    assert settings.trusted_proxies == ["127.0.0.1"]
    app = create_app(settings, rate_limits={"total_limit": 1})
    async with client(app) as c:
        h = {"X-Sagaloom-Secret": "s"}
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "1.1.1.1"})).status_code == 200
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "2.2.2.2"})).status_code == 200
        assert (await c.get("/api/worlds", headers={**h, "X-Forwarded-For": "1.1.1.1"})).status_code == 429


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
    app = build(total_limit=5, clock=clock, trusted_proxies=PEER)
    async with client(app) as c:
        for i in range(3):
            await c.get("/api/worlds", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        limiter = limiter_of(app)
        assert len(limiter._totals) == 3
        clock.now += 61
        await c.get("/api/worlds", headers={"X-Forwarded-For": "10.0.1.1"})
        assert list(limiter._totals) == ["10.0.1.1"]


async def test_key_count_stays_bounded_under_rotating_xff():
    app = build(total_limit=50, max_keys=100, clock=Clock(), trusted_proxies=PEER)
    honest = {"X-Forwarded-For": "5.5.5.5"}
    honest_codes = []
    async with client(app) as c:
        for i in range(1000):
            spoof = {"X-Forwarded-For": f"10.{i // 256}.{i % 256}.1"}
            assert (await c.get("/api/worlds", headers=spoof)).status_code == 200
            if i % 10 == 0:
                honest_codes.append((await c.get("/api/worlds", headers=honest)).status_code)
            limiter = limiter_of(app)
            assert len(limiter._totals) <= 100 and len(limiter._turns) <= 100
    # The honest client stays recent, so it is never evicted and is still limited at total_limit.
    assert honest_codes[:50] == [200] * 50
    assert set(honest_codes[50:]) == {429}


async def test_eviction_drops_least_recent_key():
    app = build(total_limit=2, max_keys=2, clock=Clock(), trusted_proxies=PEER)
    async with client(app) as c:

        async def hit(ip: str) -> int:
            return (await c.post("/api/threads/x/messages", headers={"X-Forwarded-For": ip})).status_code

        assert [await hit("1.1.1.1"), await hit("2.2.2.2"), await hit("1.1.1.1")] == [200, 200, 200]
        assert await hit("1.1.1.1") == 429  # 1.1.1.1 is at its limit, and is now the most recent
        assert await hit("3.3.3.3") == 200  # full: 2.2.2.2 is the least recently hit, so it goes
        limiter = limiter_of(app)
        assert list(limiter._totals) == ["1.1.1.1", "3.3.3.3"]
        assert list(limiter._turns) == ["1.1.1.1", "3.3.3.3"]
        # The accepted cost of bounded memory: an evicted key starts a fresh window.
        assert await hit("2.2.2.2") == 200
        assert list(limiter._totals) == ["3.3.3.3", "2.2.2.2"]


async def test_eviction_sweeps_expired_keys_first():
    clock = Clock()
    app = build(total_limit=5, max_keys=3, clock=clock, trusted_proxies=PEER)
    async with client(app) as c:
        await c.get("/api/worlds", headers={"X-Forwarded-For": "1.1.1.1"})
        await c.get("/api/worlds", headers={"X-Forwarded-For": "2.2.2.2"})
        clock.now += 30
        await c.get("/api/worlds", headers={"X-Forwarded-For": "3.3.3.3"})
        clock.now += 31  # 1.1.1.1 and 2.2.2.2 have expired, 3.3.3.3 has not
        limiter = limiter_of(app)
        limiter._last_sweep = clock.now  # keep the periodic sweep out of it
        await c.get("/api/worlds", headers={"X-Forwarded-For": "4.4.4.4"})
        # Both expired keys go, not just the least recent one.
        assert list(limiter._totals) == ["3.3.3.3", "4.4.4.4"]
