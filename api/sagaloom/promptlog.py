"""Prompt capture (R20.1, R20.2): every chat-model request is recorded as sent, and the
response is filled in when the call ends. Records are stored per thread so they survive a
refresh, and are emitted live as `llm_request` / `llm_response` events."""

import builtins
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import LLMResult
from pydantic import BaseModel, Field

from sagaloom.config import Settings
from sagaloom.models import RoleUsage, TurnUsage, Usage
from sagaloom.usage import extract_usage

# R20.1: these keys are never recorded, wherever they appear.
DROPPED_KEYS = frozenset({"api_key", "openai_api_key", "authorization", "headers"})
REDACTED = "[redacted]"
_ROLE_EXPR = "json_extract(record, '$.role')"
_COLUMNS = "id, thread_id, run_id, started_at, record, user_id"


def _month_start(now: datetime) -> datetime:
    """The first instant of `now`'s calendar month in UTC."""
    now = now.astimezone(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def next_month_start(now: datetime) -> datetime:
    """The first instant of the calendar month after `now`'s, in UTC (when a budget resets)."""
    return _month_start(_month_start(now) + timedelta(days=32))


class PromptRecord(BaseModel):
    id: str
    thread_id: str
    run_id: str
    provider: str
    model: str
    role: str | None = None
    params: dict = Field(default_factory=dict)
    request: dict  # {messages: [{role, content, name?, tool_calls?}], tools: [schema]}
    # {content, tool_calls, prompt_tokens, completion_tokens, cost_usd, latency_ms}
    response: dict | None = None
    started_at: str


def _amounts(response: dict | None) -> tuple[int, int, float]:
    """A call's (prompt tokens, completion tokens, cost); zeros for a call with no response."""
    r = response or {}
    return (
        int(r.get("prompt_tokens") or 0),
        int(r.get("completion_tokens") or 0),
        float(r.get("cost_usd") or 0.0),
    )


class PromptLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._ready = False
        self._ready_lock = threading.Lock()  # sync routes run in a thread pool

    def _create(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS prompt_log ("
            "id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, run_id TEXT NOT NULL, "
            "started_at TEXT NOT NULL, record TEXT NOT NULL)"
        )
        # M5 (spec §5.2): whose cost a call is, the owner of its thread's world when it ran. A
        # column, not part of the record, so it outlives the thread; NULL for records from before
        # M5 until `backfill_user_ids` fills them.
        if "user_id" not in {row[1] for row in conn.execute("PRAGMA table_info(prompt_log)")}:
            conn.execute("ALTER TABLE prompt_log ADD COLUMN user_id TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS prompt_log_thread ON prompt_log(thread_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS prompt_log_user ON prompt_log(user_id, started_at)")
        # `list_by_role` filters in SQL on this exact expression, so the index serves it.
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS prompt_log_role ON prompt_log({_ROLE_EXPR}, started_at)"
        )
        conn.commit()

    def _connect(self) -> sqlite3.Connection:
        """A connection to an existing table; the schema is created once per instance."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        if not self._ready:
            with self._ready_lock:
                if not self._ready:
                    try:
                        self._create(conn)
                    except BaseException:
                        conn.close()
                        raise
                    self._ready = True
        return conn

    def add(self, record: PromptRecord, *, user_id: str | None = None) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                f"INSERT OR REPLACE INTO prompt_log ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.thread_id,
                    record.run_id,
                    record.started_at,
                    record.model_dump_json(),
                    user_id,
                ),
            )

    def backfill_user_ids(self, owner_of_thread: Callable[[str], str | None]) -> int:
        """Fills `user_id` on records that have none with the owner of their thread's world
        (`owner_of_thread`, one call per thread). A thread that is gone, or whose world has no
        owner, stays NULL: it counts for nobody. Returns the number of records filled."""
        with closing(self._connect()) as conn:
            tids = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT thread_id FROM prompt_log WHERE user_id IS NULL"
                ).fetchall()
            ]
        owners = {tid: owner for tid in tids if (owner := owner_of_thread(tid)) is not None}
        if not owners:
            return 0
        with closing(self._connect()) as conn, conn:
            return sum(
                conn.execute(
                    "UPDATE prompt_log SET user_id = ? WHERE thread_id = ? AND user_id IS NULL",
                    (owner, tid),
                ).rowcount
                for tid, owner in owners.items()
            )

    def reassign_user(self, old_user_id: str, new_user_id: str) -> int:
        """Moves every record of `old_user_id` to `new_user_id` (`scripts/reassign_owner.py`);
        returns the number of records moved."""
        with closing(self._connect()) as conn, conn:
            return conn.execute(
                "UPDATE prompt_log SET user_id = ? WHERE user_id = ?", (new_user_id, old_user_id)
            ).rowcount

    def complete(self, id: str, response: dict) -> None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT record FROM prompt_log WHERE id = ?", (id,)).fetchone()
            if row is None:
                return
            rec = PromptRecord.model_validate_json(row[0]).model_copy(update={"response": response})
            conn.execute("UPDATE prompt_log SET record = ? WHERE id = ?", (rec.model_dump_json(), id))

    def list(self, thread_id: str) -> list[PromptRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT record FROM prompt_log WHERE thread_id = ? ORDER BY started_at, rowid",
                (thread_id,),
            ).fetchall()
        return [PromptRecord.model_validate_json(r[0]) for r in rows]

    def list_by_role(
        self, role: str, limit: int = 20, user_id: str | None = None
    ) -> "builtins.list[PromptRecord]":
        """The newest records of one model role (e.g. `guard`), newest first; only `user_id`'s
        when given, else everyone's (ownerless records too)."""
        mine, args = (" AND user_id = ?", [user_id]) if user_id is not None else ("", [])
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT record FROM prompt_log WHERE {_ROLE_EXPR} = ?{mine} "
                "ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (role, *args, limit),
            ).fetchall()
        return [PromptRecord.model_validate_json(r[0]) for r in rows]

    def total_usage(self, user_id: str | None = None) -> Usage:
        return self.usage(user_id=user_id)

    def usage(
        self, thread_id: str | None = None, run_id: str | None = None, user_id: str | None = None
    ) -> Usage:
        """Sum of the recorded calls (agent, judge, extractor): the single source of truth for
        per-turn (`run_id`), per-thread (`thread_id`), per-user (`user_id`, M5 spec §5.2) and
        overall usage (R16 ruling)."""
        sql, args = "SELECT record FROM prompt_log", []
        where = [
            (c, v)
            for c, v in (("thread_id", thread_id), ("run_id", run_id), ("user_id", user_id))
            if v is not None
        ]
        if where:
            sql += " WHERE " + " AND ".join(f"{c} = ?" for c, _ in where)
            args = [v for _, v in where]
        return self._sum(sql, args)

    def month_spend(self, user_id: str, now: datetime) -> float:
        """`user_id`'s cost in US$ over the calendar month (UTC) that holds `now` (spec §5.5a).
        `started_at` is stored as a UTC ISO time, so the window compares as text."""
        # Summed in SQL over the `(user_id, started_at)` index: it runs before every AI action.
        # A call with no response (or no cost) counts 0, as in `_amounts`.
        with closing(self._connect()) as conn:
            (total,) = conn.execute(
                "SELECT TOTAL(CAST(json_extract(record, '$.response.cost_usd') AS REAL)) "
                "FROM prompt_log WHERE user_id = ? AND started_at >= ? AND started_at < ?",
                [user_id, _month_start(now).isoformat(), next_month_start(now).isoformat()],
            ).fetchone()
        return float(total)

    def _sum(self, sql: str, args: "builtins.list") -> Usage:
        """The summed amounts of the records `sql` selects."""
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, args).fetchall()
        prompt = completion = 0
        cost = 0.0
        for (raw,) in rows:
            p, c, usd = _amounts(PromptRecord.model_validate_json(raw).response)
            prompt += p
            completion += c
            cost += usd
        return Usage(prompt_tokens=prompt, completion_tokens=completion, cost_usd=cost)

    def usage_by_turn(self, thread_id: str) -> "builtins.list[TurnUsage]":
        """Per-turn (`run_id`) usage with a per-role split, oldest turn first; roles in first-seen
        order. Totals match `usage(thread_id, run_id)` (R16 ruling)."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT record FROM prompt_log WHERE thread_id = ? ORDER BY started_at, rowid",
                (thread_id,),
            ).fetchall()
        turns: dict[str, dict[str | None, dict]] = {}
        totals: dict[str, Usage] = {}  # records are inserted at request start, so rowid order is `started_at` order: sums match `usage()`
        for (raw,) in rows:
            rec = PromptRecord.model_validate_json(raw)
            p, c, usd = _amounts(rec.response)
            a = turns.setdefault(rec.run_id, {}).setdefault(
                rec.role,
                {"role": rec.role, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
            )
            a["calls"] += 1
            a["prompt_tokens"] += p
            a["completion_tokens"] += c
            a["cost_usd"] += usd
            t = totals.setdefault(rec.run_id, Usage())
            t.prompt_tokens += p
            t.completion_tokens += c
            t.cost_usd += usd
        return [
            TurnUsage(
                turn_id=run_id,
                usage=totals[run_id],
                by_role=[RoleUsage(**a) for a in roles.values()],
            )
            for run_id, roles in turns.items()
        ]

    def usage_by_model(self, user_id: str | None = None) -> "builtins.list[dict]":
        """Calls, tokens and cost per (role, model) over `user_id`'s recorded calls, or every
        call when None (Studio usage panel)."""
        mine, args = (" WHERE user_id = ?", (user_id,)) if user_id is not None else ("", ())
        with closing(self._connect()) as conn:
            rows = conn.execute(f"SELECT record FROM prompt_log{mine}", args).fetchall()
        agg: dict[tuple, dict] = {}
        for (raw,) in rows:
            rec = PromptRecord.model_validate_json(raw)
            r = rec.response or {}
            a = agg.setdefault(
                (rec.role, rec.model),
                {"role": rec.role, "model": rec.model, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
            )
            a["calls"] += 1
            a["prompt_tokens"] += int(r.get("prompt_tokens") or 0)
            a["completion_tokens"] += int(r.get("completion_tokens") or 0)
            a["cost_usd"] += float(r.get("cost_usd") or 0.0)
        return sorted(agg.values(), key=lambda a: -a["cost_usd"])


_ROLES = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}


def _find_cost(d: Any) -> float | None:
    """OpenRouter puts `cost` in the usage block; look at the places langchain may keep it."""
    if not isinstance(d, dict):
        return None
    for holder in (d, d.get("token_usage"), d.get("usage")):
        if isinstance(holder, dict) and holder.get("cost") is not None:
            try:
                return float(holder["cost"])
            except (TypeError, ValueError):
                return None
    return None


class PromptLogHandler(AsyncCallbackHandler):
    # Run inline so llm_request is emitted before the first streamed token.
    run_inline = True

    def __init__(
        self,
        log: PromptLog,
        thread_id: str,
        emit: Callable[[str, dict], None],
        *,
        settings: Settings,
        secrets: Iterable[str] = (),
        turn_id: str | None = None,
        user_id: str | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.log = log
        # Stamps `started_at`; the app passes its own clock, so the records and the monthly
        # spend (`month_spend`, the budget check) read one clock (M5 spec §5.5a).
        self.clock = clock
        self.user_id = user_id  # whose cost these calls are (M5 spec §5.2)
        self.thread_id = thread_id
        self.emit = emit
        self.settings = settings
        self.secrets = [s for s in secrets if s]
        self.turn_id = turn_id or uuid.uuid4().hex
        self._started: dict[str, float] = {}

    # ---- redaction ----

    def _clean(self, obj: Any) -> Any:
        if isinstance(obj, str):
            for s in self.secrets:
                obj = obj.replace(s, REDACTED)
            return obj
        if isinstance(obj, dict):
            return {
                str(k): self._clean(v) for k, v in obj.items() if str(k).lower() not in DROPPED_KEYS
            }
        if isinstance(obj, (list, tuple, set)):
            return [self._clean(v) for v in obj]
        if obj is None or isinstance(obj, (bool, int, float)):
            return obj
        return self._clean(str(obj))

    def _message(self, m: BaseMessage) -> dict:
        out: dict[str, Any] = {"role": _ROLES.get(m.type, m.type), "content": m.content}
        if m.name:
            out["name"] = m.name
        if isinstance(m, AIMessage) and m.tool_calls:
            out["tool_calls"] = [
                {"id": c.get("id"), "name": c["name"], "args": c["args"]} for c in m.tool_calls
            ]
        return self._clean(out)

    # ---- callbacks ----

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        invocation_params: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        params = dict(invocation_params or {})
        tools = params.pop("tools", None) or []
        model = str(params.get("model") or params.get("model_name") or "unknown")
        provider = str((metadata or {}).get("ls_provider") or "openrouter")
        request = {
            "messages": [self._message(m) for m in (messages[0] if messages else [])],
            "tools": self._clean(tools),
        }
        rec = PromptRecord(
            id=str(run_id),
            thread_id=self.thread_id,
            run_id=self.turn_id,
            provider=provider,
            model=model,
            role=(metadata or {}).get("role"),
            params=self._clean(params),
            request=request,
            started_at=self.clock().astimezone(UTC).isoformat(),  # UTC: `month_spend` compares text
        )
        self._started[rec.id] = time.monotonic()
        self.log.add(rec, user_id=self.user_id)
        self.emit(
            "llm_request",
            {"id": rec.id, "provider": provider, "model": model, "role": rec.role, "params": rec.params, **request},
        )

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        rid = str(run_id)
        gen = response.generations[0][0] if response.generations and response.generations[0] else None
        msg = getattr(gen, "message", None)
        if not isinstance(msg, AIMessage):
            msg = AIMessage(content=getattr(gen, "text", "") or "")
        usage = extract_usage(msg, self.settings)
        # Streamed calls lose OpenRouter's real cost from usage_metadata; recover it when it
        # is anywhere in the result, and only then fall back to extract_usage's estimate.
        real = next(
            (
                c
                for c in (
                    _find_cost(getattr(gen, "generation_info", None)),
                    _find_cost(response.llm_output),
                    _find_cost(msg.response_metadata),
                )
                if c is not None
            ),
            None,
        )
        started = self._started.pop(rid, None)
        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, default=str)
        out = self._clean(
            {
                "content": content,
                "tool_calls": [
                    {"id": c.get("id"), "name": c["name"], "args": c["args"]} for c in msg.tool_calls
                ],
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost_usd": real if real is not None else usage.cost_usd,
                "latency_ms": int((time.monotonic() - started) * 1000) if started else 0,
            }
        )
        self.log.complete(rid, out)
        self.emit("llm_response", {"id": rid, **out})

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._started.pop(str(run_id), None)
