"""Request body cap and per-client rate limit (R13.4, R16.4).

Both are pure ASGI middlewares: SSE responses stream, and `BaseHTTPMiddleware` buffers/interferes
with streaming. The rate limiter keeps its windows in process memory, so it is per worker, and it
holds at most `max_keys` clients.
"""

import json
import math
import re
import time
from collections import OrderedDict, deque
from collections.abc import Callable

TURN_PATH = re.compile(r"^/api/(threads/[^/]+/(messages|decisions)|worlds/[^/]+/imports)$")
HEALTH_PATH = "/api/health"


async def _json_response(send, status: int, detail: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """413 when the request body exceeds `max_bytes`, by `Content-Length` or by streamed bytes."""

    def __init__(self, app, max_bytes: int = 1_000_000):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = 0
                if declared > self.max_bytes:
                    await _json_response(send, 413, "request too large")
                    return
                break

        seen = 0
        started = False
        responded = False  # our 413 went out: drop whatever the app sends afterwards

        async def counted_receive():
            nonlocal seen, started, responded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    # FastAPI rewrites exceptions raised while parsing a body into a 400, so
                    # the 413 is sent here and the app's later response is discarded.
                    if not started and not responded:
                        responded = True
                        await _json_response(send, 413, "request too large")
                    raise _TooLarge
            return message

        async def tracked_send(message):
            nonlocal started
            if responded:
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except _TooLarge:
            pass  # intended: over the cap after the response started, the stream is cut short


class RateLimitMiddleware:
    """Sliding-window limits per client key: `turn_limit` turn requests and `total_limit`
    requests overall per `window_s`. `/api/health` is exempt.

    The key is the socket peer's address (see `client_key`); `X-Forwarded-For` is read only when
    that peer is in `trusted_proxies`. At most `max_keys` clients are tracked: a new client first
    drops the expired keys at the least recently hit end and, if the map is still full, evicts
    the least recently hit one."""

    def __init__(
        self,
        app,
        turn_limit: int = 20,
        total_limit: int = 300,
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
        trusted_proxies: frozenset[str] = frozenset(),
    ):
        self.app = app
        self.turn_limit = turn_limit
        self.total_limit = total_limit
        self.window_s = window_s
        self.clock = clock
        self.max_keys = max_keys
        self.trusted_proxies = trusted_proxies
        # Least recently hit first. Every key in `_turns` is also in `_totals`.
        self._turns: OrderedDict[str, deque[float]] = OrderedDict()
        self._totals: OrderedDict[str, deque[float]] = OrderedDict()
        self._last_sweep = clock()

    def client_key(self, scope) -> str:
        """The socket peer's address. When that peer is a trusted proxy, the right-most
        `X-Forwarded-For` hop that is not itself a trusted proxy (the hops left of it are
        whatever the client chose to send); if there is none, the proxy's own address."""
        client = scope.get("client")
        peer = client[0] if client else "unknown"
        if peer not in self.trusted_proxies:
            return peer
        # Repeated headers are one list, joined in order (RFC 9110 5.3).
        values = [v.decode("latin-1") for n, v in scope["headers"] if n == b"x-forwarded-for"]
        hops = [h.strip() for h in ",".join(values).split(",")]
        for hop in reversed(hops):
            if hop and hop not in self.trusted_proxies:
                return hop
        return peer

    def _admit(self, key: str, now: float) -> None:
        """Mark `key` as the most recent client, making room for it if it is new."""
        if key in self._totals:
            self._totals.move_to_end(key)
            if key in self._turns:
                self._turns.move_to_end(key)
            return
        if len(self._totals) >= self.max_keys:
            self._sweep_front(now)
        # Evicting a live key forgets its window, so a client rotating through more than
        # `max_keys` spoofed keys gets a fresh one. That is the accepted cost of bounded memory.
        while self._totals and len(self._totals) >= self.max_keys:
            oldest, _ = self._totals.popitem(last=False)
            self._turns.pop(oldest, None)

    def _trim(self, hits: dict[str, deque[float]], key: str, now: float) -> deque[float]:
        q = hits.setdefault(key, deque())
        while q and q[0] <= now - self.window_s:
            q.popleft()
        return q

    def _sweep_front(self, now: float) -> None:
        """Drop the expired keys at the least recently hit end of `_totals`, stopping at the first
        live one, so a new key at the cap costs only the keys it removes. An expired key behind
        a live one (moved there by a 429, which adds no hit) waits for the periodic sweep or the
        eviction below. `_turns` is not walked: its order is by any hit, not by turn hit."""
        while self._totals:
            key, q = next(iter(self._totals.items()))
            if q and q[-1] > now - self.window_s:
                return
            del self._totals[key]
            self._turns.pop(key, None)

    def _sweep(self, now: float) -> None:
        for hits in (self._turns, self._totals):
            for key in [k for k, q in hits.items() if not q or q[-1] <= now - self.window_s]:
                del hits[key]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] == HEALTH_PATH:
            await self.app(scope, receive, send)
            return

        now = self.clock()
        if now - self._last_sweep >= self.window_s:
            self._last_sweep = now
            self._sweep(now)
        key = self.client_key(scope)
        self._admit(key, now)
        is_turn = scope["method"] == "POST" and TURN_PATH.match(scope["path"]) is not None
        total = self._trim(self._totals, key, now)
        turns = self._trim(self._turns, key, now)

        waits = []
        if len(total) >= self.total_limit:
            waits.append(total[0] + self.window_s - now)
        if is_turn and len(turns) >= self.turn_limit:
            waits.append(turns[0] + self.window_s - now)
        if waits:
            retry = max(1, math.ceil(max(waits)))
            await _json_response(send, 429, "rate limited", [(b"retry-after", str(retry).encode())])
            return

        total.append(now)
        if is_turn:
            turns.append(now)
        await self.app(scope, receive, send)
