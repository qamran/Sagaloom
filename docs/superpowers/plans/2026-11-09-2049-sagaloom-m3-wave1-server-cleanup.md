# Sagaloom M3 Wave 1: Server and Import-Pipeline Clean-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every server-side M3 item from the M2 reviews is fixed, or closed by a written ruling in its issue, with no user-visible change beyond what each item names.

**Architecture:** No new features. The work is: a sturdier import pipeline that Wave 3 will reuse; one writer of the commit-conflict copy; a shared, pruned memory lock; a thread listing that reads the registry instead of every checkpoint; one structured-output retry helper; bounded rate-limiter memory; docs and test hygiene. The compiled graph changes only if the user picks the tools-label option in Q2. If it does, both Mermaid docs are regenerated.

**Tech Stack:** FastAPI + LangGraph 1.2 + Chroma + SQLite (api/, `uv`, pytest-asyncio), Next.js 16 + vitest (web/, `pnpm`; touched only for the guard-log type in Task 4 and the generated types).

**Spec:** `docs/superpowers/specs/2026-11-09-2041-sagaloom-m3-design.md` §4.1, with §2, §6, §7 and §8. The findings themselves are in `internal docs/m2/*-wave{1,2,3,4,5,7,8}-*.md` and in the "Carried to M3" list at the end of `docs/superpowers/plans/2026-11-09-1527-sagaloom-m2-wave8-hardening.md`. Each task names its sources.

## Open questions for the user (answer before Tasks 6 and 7 start)

**Answered 2026-11-09 (recommended option taken; the user delegated these calls):** Q1 → **(a)**, a `TRUSTED_PROXIES` allowlist, empty by default. Q2 → **(a)**, leave the label as it is and close the item by ruling.

**Q1. Which client does the rate limiter trust? (Task 6.)** Today the API keys its limits on the first `X-Forwarded-For` hop, exactly as sent. A browser script can set that header, and the Next proxy forwards it, so rotating it bypasses the per-client limit (Wave 1 Fable M5; README limitation `:270`). Task 6 bounds the memory either way. The trust rule is a product choice:
- **(a) Trusted-proxy allowlist.** A `TRUSTED_PROXIES` setting, empty by default. The API honours `X-Forwarded-For` only when the socket peer is on the list, and then takes the right-most hop that is not a listed proxy. Otherwise it uses the socket address. This is the model of uvicorn's `--forwarded-allow-ips`, Express's `trust proxy` and Rails' `trusted_proxies`. With the default (empty), it behaves like (b) until a deployment lists its proxy.
- **(b) Socket address only.** Ignore `X-Forwarded-For` altogether. This is the default of django-ratelimit (`REMOTE_ADDR`) and nginx `limit_req` (`$binary_remote_addr`). Every request through the Next proxy then shares one bucket. That is fine for the single-user app, but gives no per-user limits behind a shared proxy.
- **(c) Keep trusting the header.** The limitation stays documented, now with bounded memory.

*Recommendation: (a).* It is safe by default and correct behind a real edge.

**Q2. Should the Agent graph name the tools? (Task 7.)** Since Wave 2 the `tools` node is drawn as `tools(tools)`. The Wave 2 Fable review declined to choose, calling it "a product call". LangGraph's `draw_mermaid()` renders node metadata under the label (`langchain_core/runnables/graph_mermaid.py:182–185`), so the node id does not need to change.
- **(a) Leave it.** Close the item by ruling: Studio's Tools section already lists every tool and its switch. LangGraph Studio also draws a `ToolNode` by its name only.
- **(b) List the tools under the label.** Pass `metadata={"tools": "<comma-separated TOOL_SPECS names>"}` to `add_node("tools", …)`. Then regenerate both Mermaid docs and re-run the web Mermaid tests. LangSmith run trees show a tool list in a similar way. The cost: `test_diagram.py` requires the docs to equal `draw_mermaid()` byte for byte, so both docs' blocks gain `<hr/><small><em>…</em></small>`. GitHub renders Mermaid with `securityLevel: strict`, so that HTML may show escaped in the README.

*Recommendation: (a).* There is less churn, and the information is already one click away.

## Rulings (made in this plan)

- **R1. Fell-through items are in scope.** Several server-side minors were ruled "Wave 8" in an M2 review but never made the Wave 8 cut or the "Carried to M3" list. Design §4 says an M3 item missing from §4.1 is in scope, and these are its closest kin. They are tagged **[fell through]** where they appear:
  - Wave 5 M8: one invalid candidate fails the whole chunk.
  - Wave 5 T1: the bare import-note test asserts one key.
  - Wave 2 T1: `test_messages_injection_is_required` does not assert `ValidationError`.
  - Wave 2 T3: the loose role filter in the prompt-record test.
  - Wave 1 T1: no route test for clearing `agent_system_prompt` with null; `settings_store` import order.
  - Wave 1 T5: a malformed `Content-Length`.
  - Wave 4 T1: the renamed-key test shape and the two `test_myth.py` nits.
  - Wave 1 wave-fix: guard retry on every `APIError`, and the guard docstring.
- **R2. "Parallel-collapse `ToolMessage` id" moves from §4.2 to this wave.** It is API code (`tools/canon_tools.py:297–298` with the `merge_proposals` reducer), so it belongs in Task 2. **M3 Wave 2's plan should drop it.**
- **R3. Wave 7 "API-side M12 test gaps": nothing to place.** All three Wave 7 M12 gaps are web-side (`EntryView` page test, the `ChatPage` `getEntries` mock, the `secrets.tsx` stale `"true"`), so they belong to M3 Wave 2. Task 7 records this ruling in its issue.
- **R4. Not taken here:** Wave 2 M2/M3 and the all-or-nothing `gather` in `wiki/client.py`. They were ruled **Wave 6** and belong to M3 Wave 3's shared client (design §5.3).
- **R5. The cheaper thread listing (design §8, builder's call)** uses summary columns on the registry row. They are cleared when a turn takes the thread's lock, written once from a single `aget_state` just before the turn's terminal event, and filled lazily for rows that have none (pre-M3 data, or a turn cut off at shutdown). Because the clear happens at turn start, a turn cancelled mid-way leaves no stale summary. A running thread is always read live.
- **R6. A malformed `Content-Length` keeps today's handling** (it is read as 0). The streamed byte counter still enforces the cap, and a test proves that. h11 rejects such a header before ASGI in production.

## Global Constraints

- Work goes on `main`. Every commit has `Refs: #N`, and the last commit of an issue has `Closes: #N`. Every commit ends with `Co-Authored-By: Claude <model> <noreply@anthropic.com>`, naming the builder's model (`Claude Opus 5.5` or `Claude Sonnet 5.5`).
- Issues in both repos, milestone "M3": **#70–#77** for Tasks 1–8, and **#78** for the Fable wave-review fixes. (#69, the docs issue for the M3 design and wave plans, is not a task here.) Issue bodies use Aim / What was done / Success criteria / Status / Reviews / Requirements / Commits. Every review finding and its resolution goes in the issue's Reviews section, in both repos.
- Never read or print `api/.env` or `web/.env.local`. Never call Gemini or any real model: unit tests use fakes. Only models in `api/sagaloom/allowed_models.json` are used.
- The SSE event set does not change: `token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`.
- These invariants hold at the end of every task:
  - tools never write;
  - only `commit` writes canon, after `check` and an approve;
  - provenance is server-set and never becomes trusted again;
  - the agent never sees a secret's text;
  - the PromptLog stays verbatim;
  - the guard fails closed;
  - the memory verbatim gate holds;
  - imported text stays verbatim and untrusted.
- A clean-up changes no user-visible behaviour beyond what its item names.
- Run the API as a single process (the commit guarantee). Keep `langchain-openai` pinned `<1.8`.
- After any change to an API model that appears in `web/lib/openapi.json`, run `pnpm types:gen` at the root and commit both generated files. Tasks 1 and 2 do this. If the compiled graph or its labels change (Task 7, Q2 (b)), regenerate the README and `docs/requirements.md` Mermaid blocks from `draw_mermaid()`. `api/tests/graph/test_diagram.py` pins both.
- **Full verification** at the end of every task:
  - `cd api && uv run pytest -q`
  - `cd web && pnpm vitest run && pnpm lint && pnpm build` (`pnpm lint` needs a timeout over 2 minutes)
  - `pnpm types:check` at the repo root

  All must be green, and `types:check` must exit 0.
- Wave records go to `internal docs/m3/YYYY-MM-DD-HHMM-m3-wave1-*.md` (ledger, task reviews, Fable review).

## Review Focus

1. **A thread listed while its turn runs, or after the API stopped mid-turn.** `GET /threads` must show the live pending count, never a summary from before the turn. Task 4 tests: `test_running_thread_is_read_live_and_not_stored` and `test_turn_start_clears_summary`.
2. **Remember and Undo racing in two tabs of one world, while a third request arrives.** No two holders may overlap, no update may be lost, and the lock map must end empty. Task 3 test: `test_waiter_and_newcomer_never_overlap`.
3. **A 100,000-character import where every chunk fails.** The extractor's spend still reaches the client (`usage`), then `error`. No `done` is sent, and no registry row is left. Task 1 test: `test_total_extraction_failure_reports_usage_then_error`.
4. **Approve while another tab has just written the same entry, against the real Chroma store.** The note must read "entry changed since it was checked (v1 → v2); propose it again", and the stored entry must be unchanged. Task 2 tests: `test_commit_conflict_against_real_store` and `test_store_guard_catches_race_against_real_store`.
5. **One client rotating `X-Forwarded-For` on every request.** The limiter's key maps must stay at or under `max_keys`. Task 6 test: `test_key_count_stays_bounded_under_rotating_xff`.

---

## Setup (before Task 1)

- [ ] Create issues #70–#77 and #78 in both repos, in order, with the body sections above and the label `status: to do`. Record the wave base (HEAD before Task 1) in the ledger.

---

### Task 1 (#70): Import pipeline robustness

Builder: **Opus 5.5** (untrusted-text extraction path; M3 Wave 3 reuses it).

Sources:
- Wave 5 Fable M1 follow-up (U+2028/U+2029/U+0085), M8 [fell through], M12 and the T1 import-note test [fell through];
- the Wave 5 ledger T2 lines;
- the Wave 8 Fable §6.2 Wave 5 row.

**Files:**
- Modify:
  - `api/sagaloom/web/imports.py`
  - `api/sagaloom/web/sse.py`: `_ev` → `event`, `_drain` → `drain`, `sse_response`
  - `api/sagaloom/web/routes.py`: the `NewImport.filename` pattern; drop `_first_line`
  - `api/sagaloom/importing/extract.py`
  - `api/sagaloom/store/canon.py`: `name_index`, `find_by_name`
  - `api/sagaloom/text.py`: `first_line`
  - `docs/requirements.md` (the R19.2 note)
  - regenerated `web/lib/openapi.json` and `web/lib/api-types.gen.ts`
- Test: `api/tests/web/test_imports.py`, `api/tests/importing/test_extract.py`, `api/tests/store/test_canon.py`, `api/tests/web/test_sse.py`

**Interfaces:**
- Produces:
  - `sagaloom.text.first_line(text: str) -> str`: the first non-blank line, stripped, uncut. The import title cuts it to `PASTE_TITLE_CHARS`; `extract.py` cuts it to `TITLE_CHARS`.
  - `sagaloom.web.sse.event(name: str, data: dict | None = None) -> Event` and `drain(queue: asyncio.Queue | None) -> list[Event]`: public; every import site is updated.
  - `sse_response(events: AsyncIterator[Event]) -> EventSourceResponse`: no `on_close` and no `BackgroundTask`. Both callers pass a `shielded` stream, which releases the lock itself.
- `CanonStore.name_index(world_id: str) -> dict[str, Entry]`:
  - maps `norm(name)` to an entry, for every title and alias;
  - entries are visited in id order, with `setdefault`, so it returns what `find_by_name` returns today;
  - `find_by_name(world_id, name)` becomes `self.name_index(world_id).get(norm(name))`.
- `build_import` reads canon once, off the event loop: `index = await asyncio.to_thread(store.name_index, world_id)`. Then `_resolve(index: dict[str, Entry], cand: Candidate) -> Entry | None` tries the title, then each alias.
- `_extract(llm, chunk, label, config) -> tuple[list[Candidate], list[Skipped]] | None` [fell through, Wave 5 M8]:
  - The request is unchanged: same system prompt, same wrapper, same schema, no tools.
  - It calls `with_structured_output(ExtractionOutput, include_raw=True)`.
  - When `parsed` is valid, it returns every candidate.
  - When parsing failed but the raw reply holds a JSON object with a `candidates` list (the message `content`, else the first tool call's `args`), it validates each item alone. An invalid item becomes `Skipped(title=<its "title" if a string, cut to TITLE_CHARS, else "An extracted entry">, reason=INVALID)`.
  - Anything else is a failed attempt. `None` comes back after `MAX_ATTEMPTS` failed attempts.
- Total extraction failure:
  - `import_events` yields `usage` (from `usage_fn()`, the extractor's spend), then `error` with `EXTRACTION_FAILED`.
  - It sends no `done`, and the registry row is deleted as today.
  - Graph-run failures are unchanged (`error` instead of `usage`/`done`). Update the docstrings of `sse.py` and `imports.py` and the R19.2 note to state this narrow rule.
- `import_events` iterates `_extraction` inside `async with aclosing(...)`.
- `NewImport.filename` pattern: the name part refuses `/`, `\`, and every `Cc`, `Zl` and `Zp` character, the same classes as `memory._one_line`. Use `[^/\\\p{Cc}\p{Zl}\p{Zp}]+` (pydantic's Rust regex engine). If pydantic rejects it, list `\x00-\x1f\x7f-\x9f  ` explicitly.

- [ ] **Step 1: Write the failing tests**
  - `test_imports.py`:
    - `test_total_extraction_failure_reports_usage_then_error`: the stub extractor raises on every attempt. The event names end with `["tool_result", "node", "usage", "error"]`, and there is no `done`. The `usage` data equals the fake `usage_fn()` output, and `registry.get(thread_id) is None`.
    - `test_import_closes_extraction_stream_when_closed`: monkeypatch `sagaloom.web.imports._extraction` with a generator that yields one sentinel event, then waits on an `asyncio.Event` and sets a flag in its `finally`. `import_events` yields `node start` before it enters `_extraction`, so read events until the sentinel arrives. Then `aclose()` the outer generator and assert that the flag is set.
    - Extend `test_import_rejects_bad_filename` with `"a .md"`, `"a .txt"` and `"a\x85.md"` (each 422).
    - [fell through] `test_import_note_payload_is_exact`: `import_note(plan, "notes.md").additional_kwargs == {"import": {"source": "notes.md", "first_lines": {...}, "skipped": [{"title": ..., "reason": ...}]}}`, with exact values from a two-proposal, one-skip plan, and `content` unchanged.
  - `test_canon.py`: `test_name_index_matches_find_by_name`. Entries ent_0001 "Ister" (alias "Pale Moon") and ent_0002 alias "Ister": `name_index("w1")["ister"].id == "ent_0001"`, `["pale moon"].id == "ent_0001"`, and `find_by_name` agrees for "ISTER", "pale  moon" and "nope".
  - `test_extract.py`:
    - `test_build_import_reads_canon_once`: a store spy counts `list_entries`. Two chunks with three candidates (title match, alias match, new) give exactly 1 call, and the same resolutions as before.
    - `test_name_index_runs_off_the_event_loop`: the spy records `threading.get_ident()`, which is not the loop thread's.
    - `test_one_invalid_candidate_is_skipped_alone`: the stub returns `{"raw": AIMessage(content='{"candidates":[<valid Gull Market>, {"title":"Wyrm","type":"dragon","excerpt":"…"}]}'), "parsed": None, "parsing_error": ValidationError}`. That gives one proposal for Gull Market, `Skipped("Wyrm", INVALID)`, and `failed_parts == 0`.
    - `test_unreadable_raw_reply_is_a_failed_attempt`: raw content `"not json"` twice gives `PART_FAILED`.
  - `test_sse.py`: `test_sse_response_has_no_background_task` (`sse_response(gen).background is None`).

- [ ] **Step 2: Run them to verify they fail.** Run `cd api && uv run pytest -q tests/web/test_imports.py tests/importing tests/store/test_canon.py tests/web/test_sse.py`. Each new test must FAIL for the stated reason: no `usage`, no `aclosing`, the pattern accepts the name, no `name_index`, or the whole chunk fails.

- [ ] **Step 3: Implement** the interfaces above. Update the existing extractor stubs for `include_raw=True` (they return `{"raw": …, "parsed": …, "parsing_error": None}`).

- [ ] **Step 4: Run the Step 2 command.** Expected: PASS. Then run `pnpm types:gen` at the root, because the `NewImport` pattern is in the OpenAPI schema.

- [ ] **Step 5: Full verification, then commit**
```bash
git add api/sagaloom api/tests docs/requirements.md web/lib/openapi.json web/lib/api-types.gen.ts
git commit -m "fix: import pipeline robustness (aclosing, usage on failure, one canon read, per-candidate validation, filename separators)" -m "Refs: #70" -m "Closes: #70" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2 (#71): Version, commit copy and proposal tool message

Builder: **Opus 5.5** (the commit invariant).

Sources:
- Wave 8 Fable M6, M7 and the §6.1 T2/T3/T5 rows;
- the Wave 8 ledger T2 and T3 lines;
- Wave 4 Fable M9 / T1 (moved here by R2).

**Files:**
- Modify:
  - `api/sagaloom/models.py` (`Entry.version`)
  - `api/sagaloom/store/canon.py` (the `upsert_entry` comparison; `find_mentions`)
  - `api/sagaloom/graph/nodes.py` (`_apply`, `_apply_locked`, `make_commit_node`)
  - `api/sagaloom/tools/canon_tools.py:297–298`
  - `api/sagaloom/web/routes.py:246`
  - regenerated `web/lib/openapi.json` and `web/lib/api-types.gen.ts`
- Test: `api/tests/test_models.py` (new, or the nearest existing model test), `api/tests/store/test_canon.py`, `api/tests/graph/test_graph.py`, `api/tests/tools/test_canon_tools.py`, `api/tests/test_seed.py`, `api/tests/web/test_routes.py`

**Interfaces:**
- `Entry.version: int = Field(default=1, ge=1)`. This is checkpoint-safe because no writer has ever stored v0 (Wave 8 M7). In `upsert_entry`, the comparison becomes `(0 if actual is None else actual) != expected_version`.
- `conflict_reason(e: VersionConflictError) -> str` in `nodes.py` is the **only** writer of the conflict copy:
  - `actual is None` → `entry {id} no longer exists`;
  - `expected == 0` → `an entry with id {id} already exists; propose it again`;
  - otherwise → `entry changed since it was checked (v{expected} → v{actual}); propose it again`.
- `_apply_locked` raises `VersionConflictError` for its own checks:
  - missing entry: `VersionConflictError(p.entry_id or "", p.before.version if p.before else 0, None)`;
  - stale `before`: `VersionConflictError(current.id, p.before.version, current.version)`.

  `_apply` maps every `VersionConflictError` through `conflict_reason` to `_CommitFailed`.
- `commit` gives a world mismatch its own refusal, checked before the "not checked and approved" one, with outcome `refused`: `Review: {pid} was not committed: it was proposed in another world.` (Wave 8 T3; no web test pins the old copy.)
- `CanonStore.find_mentions(world_id: str, entry: Entry) -> list[Entry]` counts text mentions only; the `links` parameter is removed. The mentions route calls it without the argument. Callers that want links use `find_dependents`.
- The proposal `ToolMessage` text becomes `f"Proposal to {action} {label} is awaiting the author's review."`. The id is dropped because, for two parallel calls on one entry, the reducer keeps the first id and the tool cannot know that. The agent never uses the id (decisions come from the author).

- [ ] **Step 1: Write the failing tests**
  - `test_entry_version_must_be_positive`: `Entry(id="ent_0001", world_id="w", title="T", type="place", body="", version=0)` raises `ValidationError`.
  - `test_commit_maps_create_race_to_already_exists`: the store's `upsert_entry` raises `VersionConflictError("ent_0099", 0, 1)`. The note is `Review: p_x approved, but the commit failed: an entry with id ent_0099 already exists; propose it again. Nothing was written.`, with outcome `failed`.
  - `test_conflict_copy_has_one_writer`: `inspect.getsource(sagaloom.graph.nodes).count("entry changed since it was checked") == 1`.
  - `test_commit_refuses_other_world_with_its_own_copy`: the note is `Review: p_x was not committed: it was proposed in another world.`, with outcome `refused`; the proposal stays pending.
  - [Review Focus 4] `test_commit_conflict_against_real_store`. Use the conftest `store` (real Chroma, fake embeddings) and `make_commit_node(store)`. Store ent_0001 at v1. Build an approved, checked update proposal with `before` at v1. Bump the stored entry to v2 with `store.upsert_entry`, then run commit. The note contains `entry changed since it was checked (v1 → v2); propose it again`, and the store still holds v2's body.
  - [Review Focus 4] `test_store_guard_catches_race_against_real_store`. Same setup, but wrap `store.get_entry` so that it returns the v1 entry and then writes v2 before returning. This makes the node's own check pass and the store's guard raise. The note is the same, and the store is unchanged.
  - `test_find_mentions_is_text_only`: an entry linked only by a link is not returned. Switch `test_canon.py:85–94`, `test_seed.py:51` and `test_routes.py:393` to `find_dependents` (keeping what they assert). `test_canon.py:97–102` and `test_seed.py:159` just drop `links=False`.
  - Update `test_canon_tools.py:110` to `"Proposal to create Ostra is awaiting the author's review."`, and add an update case.

- [ ] **Step 2: Run them to verify they fail.** Run `cd api && uv run pytest -q tests/store tests/graph/test_graph.py tests/tools tests/test_seed.py tests/web/test_routes.py`. Expected: the new tests FAIL.

- [ ] **Step 3: Implement**, then run `pnpm types:gen` (`Entry` is in the schema).

- [ ] **Step 4: Full verification, then commit**
```bash
git commit -m "fix: one writer of the commit conflict copy; Entry.version >= 1; world-mismatch refusal; text-only find_mentions" -m "Refs: #71" -m "Closes: #71" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3 (#72): Memory: one pruned lock per world, per-update failure, `MemoryResult.reason`

Builder: **Opus 5.5** (concurrency; the memory verbatim gate).

Sources:
- Wave 3 Fable triage (locks dict, `agent_note` wording match) and Q5 (`forget` takes no lock);
- the Wave 3 ledger wave-fix line (a mid-batch store failure reports earlier writes as not stored).

**The prune trap.** Do not copy `_take_turn`'s prune. That lock never has waiters, because the route answers 409. The memory lock does have waiters (two threads, one world). If the entry is deleted on release while a woken waiter has not resumed yet, a newcomer's `setdefault` makes a fresh lock and runs alongside the waiter.

**Files:**
- Create: `api/sagaloom/locks.py`, `api/tests/test_locks.py`
- Modify:
  - `api/sagaloom/models.py` (`MemoryResult`)
  - `api/sagaloom/memory.py` (`apply_updates`, `agent_note`)
  - `api/sagaloom/graph/nodes.py` (`make_remember_node`)
  - `api/sagaloom/graph/build.py`
  - `api/sagaloom/web/app.py` (`AppDeps`, `build_graph` call)
  - `api/sagaloom/web/routes.py` (`delete_memory`)
- Test: `api/tests/test_memory.py`, `api/tests/graph/test_graph.py`, `api/tests/web/test_memory_routes.py`

**Interfaces:**
- `class KeyedLocks` in `sagaloom/locks.py`:
  - `def hold(self, key: str) -> contextlib.AbstractAsyncContextManager[None]`;
  - `def __len__(self) -> int` (the number of keys held or awaited).
  - It keeps a per-key count, incremented before awaiting the lock and decremented in a `finally` after release, so a cancelled waiter decrements too. The key's lock is deleted when the count reaches 0.
- `AppDeps.memory_locks: KeyedLocks = field(default_factory=KeyedLocks)`.
- `build_graph(..., memory_locks: KeyedLocks | None = None)` (None → a new `KeyedLocks`), and `make_remember_node(memory_store, locks: KeyedLocks)`. `_open_runtime` passes `deps.memory_locks`.
- `delete_memory` runs `forget` inside `async with d.memory_locks.hold(world_id)`.
- `MemoryReason = Literal["stored", "not_said", "full", "invalid", "unavailable"]` in `models.py`, and `MemoryResult.reason: MemoryReason`, required. Every `MemoryResult(...)` site sets it (`grep -rn "MemoryResult(" api/sagaloom`). Checkpoints hold only `model_dump()` dicts in `additional_kwargs`, so old threads still load. The web reads `memory[*]` dicts, and the field is additive.
- `agent_note(r)` switches on `r.reason`. It never compares note strings. Its output is unchanged for every reason.
- `apply_updates`:
  - A failing `read_preferences` propagates (the node's `except` reports every update `unavailable`, as today).
  - When `store.aput` raises, that update and every later one get `reason="unavailable"` and `note=unavailable_note(key)`. Earlier results keep `stored=True`. One `log.exception`.

- [ ] **Step 1: Write the failing tests**
  - `test_locks.py`:
    - [Review Focus 2] `test_waiter_and_newcomer_never_overlap`: A holds key "w"; B awaits `hold("w")`; A releases; C calls `hold("w")` in the same loop tick. Record `(enter, exit)` per holder: no two intervals overlap.
    - `test_key_removed_when_last_holder_leaves` (`len(locks) == 0`).
    - `test_key_kept_while_a_waiter_exists`.
    - `test_cancelled_waiter_does_not_leak` (after cancel and release, `len == 0`).
  - `test_memory.py`:
    - `test_store_failure_mid_batch_keeps_earlier_results`: the second `aput` raises. The results are `[stored, unavailable, unavailable]`, and the first value is in the store.
    - `test_reason_set_for_each_outcome` (stored, not_said, full, invalid).
    - `test_agent_note_reads_reason_not_note_text`: `MemoryResult(key="tone", value="x", stored=False, note="anything", reason="not_said")` gives `"Not remembered: it wasn't something the author said (tone)"`.
  - `test_graph.py`: `test_remember_uses_the_shared_locks`. Pass a `KeyedLocks` to `build_graph`, then run a remember turn: the lock map is empty afterwards, and a spy on `hold` saw the world id.
  - `test_memory_routes.py`: `test_forget_waits_for_the_world_lock`. Hold `deps.memory_locks.hold(world)` in the test, start `DELETE /memory`, and assert that it has not completed. Release it, and it completes with 200.

- [ ] **Step 2: Run them to verify they fail.** Run `cd api && uv run pytest -q tests/test_locks.py tests/test_memory.py tests/graph/test_graph.py tests/web/test_memory_routes.py`.

- [ ] **Step 3: Implement**, then run the Step 2 command. Expected: PASS. Also run the planted-memory unit tests: `uv run pytest -q -k "planted or remember"`.

- [ ] **Step 4: Full verification, then commit** with `Refs: #72`, `Closes: #72`, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 4 (#73): Cheaper thread listing, registry schema once, prompt-log role query, guard log `error`

Builder: **Opus 5.5** (cache invalidation across turns).

Sources:
- M1 M10 and Wave 4 Fable M5 (`GET /threads` cost);
- the Wave 5 ledger T1 (`PRAGMA table_info` on every connect);
- Wave 1 Fable M8 (`list_by_role` full scan) and M6 (guard log `unknown`).

**Files:**
- Create: `api/sagaloom/web/thread_list.py`
- Modify:
  - `api/sagaloom/store/threads.py`
  - `api/sagaloom/web/routes.py`: `list_threads`, `_take_turn`, `_stream_run`, `post_import`, `guard_log`
  - `api/sagaloom/promptlog.py`
  - `web/lib/types.ts:280` (`GuardLogRow["verdict"]` gains `"error"`) and `web/components/GuardrailsPanel.tsx:8–12` (a `BADGE` entry for `error`)
- Test: `api/tests/store/test_threads.py`, `api/tests/web/test_routes.py`, `api/tests/test_promptlog.py`, `api/tests/web/test_settings_routes.py`, `web/tests/GuardrailsPanel.test.tsx`

**Interfaces:**
- `store/threads.py`:
  - `class ThreadSummary(BaseModel)` has `pending: int`, `badge: str | None` (a plain `str`, so `store` does not import `check`; `thread_list.py` narrows it), `approved: int`, `rejected: int`, `title: str | None` (the derived title).
  - `ThreadInfo.summary: ThreadSummary | None = None`.
  - New nullable columns: `pending`, `badge`, `approved`, `rejected`, `derived_title`. `pending IS NULL` means "not summarised".
  - Schema creation and migration run **once per registry instance** (a `self._ready` flag). The migration adds `kind` to an M1 table and the five columns to an M2 table.
  - `set_summary(thread_id: str, summary: ThreadSummary | None) -> None` (None clears; an unknown id is a no-op).
  - `set_summary_if_unset(thread_id, summary) -> None` (`UPDATE … WHERE pending IS NULL`).
- `web/thread_list.py`:
  - `summarise(state, title: str | None) -> ThreadSummary` is pure: today's per-thread body of `list_threads`.
  - `async def refresh_summary(deps, thread_id: str) -> None`:
    - it returns at once if the registry row is gone (a failed import);
    - otherwise it runs one `aget_state` and calls `set_summary`;
    - on an exception it logs and leaves the summary NULL.
  - `def with_summary(events: AsyncIterator[Event], refresh: Callable[[], Awaitable[None]]) -> AsyncIterator[Event]` awaits `refresh()` **before** yielding the terminal `done` or `error`, or at the end if neither comes.
  - `async def list_rows(deps, *, pending: bool, world_id: str | None, kind: ThreadKind | None) -> list[dict]`:
    - rows come newest first;
    - for a row with a summary whose lock is not held, the row comes from the summary, with no checkpoint read;
    - otherwise it runs `aget_state` and `summarise`, then stores the result with `set_summary_if_unset`, and only if the lock is not held after the await either;
    - an unreadable checkpoint is skipped and logged, as today.
- `routes.py`:
  - `_take_turn` calls `threads.set_summary(thread_id, None)` right after acquiring the lock.
  - `_stream_run` and `post_import` wrap their event stream in `with_summary(…, lambda: refresh_summary(d, thread_id))` inside `shielded`.
  - `list_threads` delegates to `list_rows`.
- **Produces (M3 Wave 2's pill relies on this):** `GET /threads` reads no checkpoint for a thread that has a summary and is not running. The JSON row shape is unchanged: `{thread_id, world_id, pending, created_at, kind, title, badge, approved, rejected, running}`.
- `promptlog.py`:
  - `CREATE TABLE`/`CREATE INDEX` run once per instance.
  - New expression index: `prompt_log_role ON prompt_log(json_extract(record, '$.role'), started_at)` (SQLite 3.50).
  - `list_by_role` becomes `SELECT record … WHERE json_extract(record, '$.role') = ? ORDER BY started_at DESC, rowid DESC LIMIT ?`. There is no column migration.
- `guard_log`: `verdict` is `"error"` when `rec.response is None` (a call that raised); `"unknown"` stays for a response that is present but unparseable.

- [ ] **Step 1: Write the failing tests**
  - `test_threads.py`:
    - `test_schema_checked_once_per_registry`: spy on the migration helper; `create`, `get` and `list` run it once.
    - `test_migrates_m1_and_m2_tables`.
    - `test_set_summary_round_trip_and_clear`.
    - `test_set_summary_if_unset_never_overwrites`.
  - `test_routes.py`, with a fake graph that counts `aget_state`:
    - `test_list_threads_reads_no_checkpoint_after_a_turn` (after a message turn ends, `GET /threads` makes 0 calls).
    - `test_list_threads_summarises_legacy_rows_once` (first GET: 1 call per row; second: 0).
    - [Review Focus 1] `test_running_thread_is_read_live_and_not_stored`.
    - [Review Focus 1] `test_turn_start_clears_summary`.
    - `test_summary_refreshed_before_done`: after a decisions turn, the `done` event is read only once the row's `pending` is already 0.
    - `test_list_threads_row_shape_unchanged`: the exact keys.
    - Keep `test_list_threads_skips_unreadable_checkpoint` passing; it now exercises the lazy path.
  - `test_promptlog.py`:
    - `test_list_by_role_filters_in_sql` (10 records over 3 roles; newest-first order and `limit` honoured).
    - `test_role_index_exists` (`PRAGMA index_list`).
  - `test_settings_routes.py`: `test_guard_log_marks_a_failed_call_error` (a guard record with `response=None` gives `verdict == "error"`).
  - `GuardrailsPanel.test.tsx`: an `error` row renders its verdict with a defined class (not `undefined`).

- [ ] **Step 2: Run them to verify they fail.** Run `cd api && uv run pytest -q tests/store/test_threads.py tests/web/test_routes.py tests/test_promptlog.py tests/web/test_settings_routes.py` and `cd web && pnpm vitest run tests/GuardrailsPanel.test.tsx`.

- [ ] **Step 3: Implement**, then run the Step 2 commands. Expected: PASS.

- [ ] **Step 4: Full verification, then commit**
```bash
git commit -m "perf: thread list reads registry summaries, not every checkpoint; schema once; role query in SQL; guard log error" -m "Refs: #73" -m "Closes: #73" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5 (#74): One structured-output retry helper and module tidy-ups

Builder: Sonnet 5.5. The guard's fail-closed behaviour is pinned by existing tests, which must stay green unchanged apart from the exception type noted below.

Sources:
- Wave 3 Fable triage: the retry loop, `GEMINI_MODEL`, `_ask_judge` typing, `exc.request`;
- the Wave 1 ledger wave-fix line [fell through]: private constants, the APIError breadth, the docstring;
- Wave 2 Fable M4 and M7.

**Files:**
- Create: `api/sagaloom/structured.py`, `api/tests/test_structured.py`
- Modify:
  - `api/sagaloom/guard.py`, `api/sagaloom/router.py`, `api/sagaloom/check/contradiction.py`
  - `api/sagaloom/graph/nodes.py` (imports `ChatModelLike` from `structured`)
  - `api/sagaloom/config.py` (`GEMINI_MODEL`), `api/sagaloom/llm.py`, `api/sagaloom/studio.py`
  - `api/sagaloom/web/sse.py:59` (`exc.request.url.host`)
  - `api/sagaloom/web/routes.py:30` (`TOOL_SPECS` from `sagaloom.tools.specs`)
  - `api/sagaloom/settings_store.py`
- Test: `api/tests/test_guard.py`, `api/tests/test_router.py`, `api/tests/check/test_contradiction.py`, `api/tests/test_settings_store.py`

**Interfaces:**
- `sagaloom/structured.py` (public; nothing imports a private name across modules any more):
  - `MAX_ATTEMPTS = 2`;
  - `INVALID_REPLY: tuple[type[BaseException], ...]`, moved from `contradiction._invalid_reply_errors`;
  - `TRANSIENT_API_ERRORS = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError)`;
  - `class InvalidReply(ValueError)`;
  - `class ChatModelLike(Protocol)`, moved from `nodes.py`; `nodes.py` re-imports it, so `sagaloom.graph.nodes.ChatModelLike` still resolves;
  - `async def ask_structured(model: ChatModelLike, schema: type[T], messages: list, *, what: str, retry_transient: bool) -> T`.
- `ask_structured` behaviour:
  - Each attempt calls `ainvoke`. A `dict` reply is validated into `schema`. A reply that is not an instance of `schema`, or one that raises an `INVALID_REPLY` error, is invalid. The attempt number is logged with `what`.
  - After the last invalid reply it raises `InvalidReply`, chained to the last cause.
  - With `retry_transient`, a `TRANSIENT_API_ERRORS` exception is retried and re-raised after the last attempt.
  - Every other exception propagates at once. That includes a 4xx `APIStatusError`, which was retried before; the narrowing is named in the Wave 1 ledger.
- Callers:
  - `classify` and `route` use `retry_transient=True`. The guard node's `except Exception → "error"` still blocks the message, and the router still fails open.
  - `check_proposal` uses `retry_transient=False`. It catches `InvalidReply` where it caught `_JudgeInvalid`, so API errors still propagate and the check fails closed.
  - `_ask_judge`, `_JudgeInvalid` and `_invalid_reply_errors` are removed.
  - The docstrings say exactly this; none claims "the judge's retry policy".
- `GEMINI_MODEL` lives in `config.py`. `llm.py` and `studio.py` import it from there, and `llm.py` no longer imports `studio`.
- `DevSettingsStore` warns about unknown `enabled_tools` once per distinct stored value (it keeps the last raw value it warned about).

- [ ] **Step 1: Write the failing tests**
  - `test_structured.py`:
    - `test_retries_once_after_invalid_reply`.
    - `test_raises_invalid_reply_after_two`: it raises `InvalidReply`, and two calls were made.
    - `test_retries_transient_error_when_asked` (an `APIConnectionError`, then valid).
    - `test_does_not_retry_transient_when_not_asked`.
    - `test_client_error_is_not_retried`: an `APIStatusError` with a 400 response gives 1 call, and it propagates.
    - `test_dict_reply_is_validated`.
  - `test_guard.py`:
    - `_api_error()` becomes an `APIConnectionError`; `test_classify_raises_after_two_failures` still expects two calls.
    - New `test_classify_does_not_retry_a_400`.
    - `test_guard_node_blocks_on_invalid_reply` (graph-level: two invalid replies give the `error` verdict and the block copy).
  - `test_contradiction.py`: `test_judge_invalid_twice_fails_closed` (unchanged outcome via `InvalidReply`).
  - `test_settings_store.py`: `test_unknown_tools_warning_logged_once` (caplog: three `get()` give one warning; a different bad value gives a second).
  - `test_llm.py`: `test_llm_does_not_import_studio` (`"sagaloom.studio" not in` the import lines of `llm.py`'s source).

- [ ] **Step 2: Run them to verify they fail.** Run `cd api && uv run pytest -q tests/test_structured.py tests/test_guard.py tests/test_router.py tests/check tests/test_settings_store.py tests/test_llm.py`.

- [ ] **Step 3: Implement**, then run the Step 2 command. Expected: PASS. Then run `grep -rn "_INVALID_REPLY\|from sagaloom.check.contradiction import.*MAX_ATTEMPTS\|from sagaloom.studio import GEMINI" api/sagaloom`. Expected: no output.

- [ ] **Step 4: Full verification, then commit** with `Refs: #74`, `Closes: #74`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 6 (#75): Rate-limiter memory and the client key (Q1)

Builder: **Opus 5.5** (security control).

Sources:
- Wave 1 Fable M5 and the Wave 1 ledger T5 lines (unbounded memory under spoofed XFF; no-XFF clients share one bucket; malformed `Content-Length`);
- README limitations `:269–270`.

**Files:**
- Modify: `api/sagaloom/web/limits.py`, `README.md` (limitations and the security paragraph at `:153`)
- Only for Q1 (a): `api/sagaloom/config.py` (`trusted_proxies`) and `api/sagaloom/web/app.py` (pass it in)
- Test: `api/tests/web/test_limits.py`

**Interfaces:**
- `RateLimitMiddleware(app, turn_limit=20, total_limit=300, window_s=60.0, clock=time.monotonic, max_keys: int = 10_000, trusted_proxies: frozenset[str] = frozenset())`.
- `_turns` and `_totals` become `OrderedDict`s, and each hit moves its key to the end. When adding a key would exceed `max_keys`, the limiter first sweeps expired keys; if the map is still full, it evicts the least recently hit key from both maps. Eviction lets an evicted spoofer start a fresh window, which is the accepted cost of bounded memory; say so in a comment and in the README limitation.
- `client_key(scope) -> str` depends on the Q1 answer:
  - **(a):** if `scope["client"][0] in trusted_proxies`, take the right-most `X-Forwarded-For` hop that is not in `trusted_proxies`; otherwise use the socket host. Add `Settings.trusted_proxies: list[str] = []` (env `TRUSTED_PROXIES`, JSON list).
  - **(b):** always the socket host.
  - **(c):** unchanged.
- The body cap is unchanged (R6).

- [ ] **Step 1: Write the failing tests**
  - [Review Focus 5] `test_key_count_stays_bounded_under_rotating_xff`: `max_keys=100`, 1,000 requests, each with a distinct `X-Forwarded-For`. `len(_totals) <= 100` and `len(_turns) <= 100`, and an honest client in the middle is still limited at `total_limit`.
  - `test_eviction_drops_least_recent_key`.
  - (R6) `test_malformed_content_length_still_capped_by_stream`: header `content-length: abc` and a streamed body over `max_bytes` give 413 JSON.
  - For (a):
    - `test_xff_ignored_from_untrusted_peer`;
    - `test_rightmost_untrusted_hop_from_trusted_proxy` (`"1.1.1.1, 2.2.2.2"` via trusted `127.0.0.1` gives `2.2.2.2`; `"1.1.1.1, 10.0.0.1"` with both proxies trusted gives `1.1.1.1`).
  - For (b): `test_xff_is_ignored`.

- [ ] **Step 2: Run them to verify they fail:** `cd api && uv run pytest -q tests/web/test_limits.py`.

- [ ] **Step 2b: Check the local path (Q1 = (a)).** Read `web/app/api/proxy/[...path]/route.ts` and record in the report what it sends as `X-Forwarded-For` for a local browser. With the empty default, every proxied request is keyed by the socket peer (the Next server). Confirm the 20-turn and 300-request budgets still fit one author plus the header pill's polling. The exit demo in Task F is the end-to-end check.

- [ ] **Step 3: Implement.** Rewrite the README limitation lines to state the chosen trust rule and the bounded memory. For (a), also document `TRUSTED_PROXIES` beside the other settings. Then run the Step 2 command. Expected: PASS.

- [ ] **Step 4: Full verification, then commit** with `Refs: #75`, `Closes: #75`, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 7 (#76): Graph label (Q2), seed script report, provenance doc notes

Builder: Sonnet 5.5.

Sources:
- Wave 2 Fable M6 (the `tools` label);
- Wave 7 Fable M11 (`seed_missing` rule (b));
- the Wave 2 ledger wave-fix line (document "an empty lookup doesn't taint");
- R3 (Wave 7 M12).

**Files:**
- Modify:
  - `api/sagaloom/seed.py`, `api/scripts/seed_missing.py`
  - `README.md` (`:106`, `:262`), `docs/review-notes.md:79`, `docs/requirements.md` (the R11.4.6 row)
  - Only for Q2 (b): `api/sagaloom/graph/build.py` and the two Mermaid blocks
- Test: `api/tests/test_seed.py`; for Q2 (b), `api/tests/graph/test_diagram.py` (a new test beside the existing one)

**Interfaces:**
- `seed_missing(store, seed_dir, world_id=VELMAR_ID) -> SeedReport`:
  - `@dataclass class SeedReport` has `added: list[tuple[str, Entry]]` (seed id, stored entry) and `kept: list[tuple[str, Entry]]` (seed id, the same-type entry already at that id, rule (b)).
  - The script prints one line per kept entry: `kept {seed_id}: {entry.id} ({entry.title}) has the seed entry's type, so it is treated as the renamed seed entry`. It also keeps printing additions and "nothing missing".
- Q2 (b) only: `g.add_node("tools", make_tools_node(tools, dev), metadata={"tools": ", ".join(s["name"] for s in TOOL_SPECS)})`.

- [ ] **Step 1: Write the failing tests**
  - Update every `seed_missing` assertion in `test_seed.py` to `.added`.
  - Add `test_seed_missing_reports_rule_b_kept` (a renamed same-type entry at ent_0019 gives `kept == [("ent_0019", <it>)]` and `added == []`).
  - Q2 (b): add `test_tools_node_label_lists_every_tool` (every `TOOL_SPECS` name is in `draw_mermaid()`).

  Run `cd api && uv run pytest -q tests/test_seed.py tests/graph`. Expected: FAIL.

- [ ] **Step 2: Implement.** For Q2 (b):
  - regenerate the README and `docs/requirements.md` Mermaid blocks from `draw_mermaid()`;
  - run `cd web && pnpm vitest run tests/mermaid.test.ts` (or the file that covers `web/lib/mermaid.ts`);
  - open Studio → Agent graph once to check that the label renders, and attach a screenshot to the issue.

  For Q2 (a): close the item in the issue's Reviews section with the ruling, and change no code.

- [ ] **Step 3: Docs**
  - README `:106`: after "nothing is marked untrusted", add "; a lookup that finds no pages marks nothing either".
  - README `:262`: "One successful lookup" → "One lookup that returns at least one page".
  - review-notes `:79`: "A failed lookup does not taint, since nothing was fetched" → "A failed lookup, or one that finds no pages, does not taint, since nothing was fetched".
  - R11.4.6 "Done when": add "a lookup with no results leaves `source = user`".

  In the issue's Reviews section, record R3 (Wave 7 M12 is web-side: M3 Wave 2).

- [ ] **Step 4: Full verification, then commit** with `Refs: #76`, `Closes: #76`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 8 (#77): Test hygiene and warnings

Builder: Sonnet 5.5.

Sources:
- Wave 3 Fable triage: unclosed `AsyncClient`s, the `_error_event` 503 test, Pydantic `parsed` serializer warnings;
- Waves 1–2 and Wave 8: the pytest-asyncio loop-scope warning;
- the [fell through] test items in R1.

**Files:**
- Modify:
  - `api/pyproject.toml`
  - `api/sagaloom/llm.py` (`install_warning_filters`), `api/sagaloom/web/app.py` (call it in `_open_runtime`), `api/tests/eval/conftest.py` (call it)
  - `api/tests/test_llm.py`, `api/tests/web/test_sse.py`, `api/tests/web/test_studio_routes.py`, `api/tests/web/test_settings_routes.py`
  - `api/tests/tools/test_canon_tools.py:279–287`
  - `api/tests/graph/test_graph.py` (the tool-toggle prompt-record assertions near `:1306`)
  - `api/tests/check/test_myth.py`

**Interfaces:**
- `pyproject.toml` `[tool.pytest.ini_options]`: `asyncio_default_fixture_loop_scope = "function"`. Safe: `tests/` defines no async fixtures, and the eval conftest's session loop applies to tests only (checked while planning).
- `install_warning_filters() -> None` in `llm.py` adds one `warnings.filterwarnings("ignore", …)`. It is keyed to the exact message that `langchain_openai` produces when it dumps a `ParsedChatCompletion` (third-party; Wave 3 Fable "declined to judge"). The builder first reproduces the warning in a test to get the exact text. Other Pydantic serializer warnings still show.

- [ ] **Step 1: Write the failing tests**
  - `test_llm.py`:
    - `test_parsed_serializer_warning_is_filtered`: reproduce the warning (dump a `ParsedChatCompletion` whose `parsed` is a pydantic model, the way langchain-openai does) inside `warnings.catch_warnings(record=True)`, after `install_warning_filters()`. No warning is recorded.
    - `test_other_serializer_warnings_still_show`.
  - `test_sse.py`: parametrise `test_gemini_error_becomes_an_error_event_with_switch_back` over `(429, "Gemini's free tier is out of requests right now.")` and `(503, "Gemini is overloaded right now.")`, using `openai.InternalServerError` for 503.
  - `test_settings_routes.py` [fell through]: `test_put_null_clears_system_prompt` (PUT `{"agent_system_prompt": "x"}`, then `null`, gives `settings.agent_system_prompt is None`).
  - `test_canon_tools.py:279` [fell through]: the injection-required test asserts `pytest.raises(ValidationError)`, with no early `return`.

  Run `cd api && uv run pytest -q tests/test_llm.py tests/web tests/tools`. Expected: the new tests FAIL.

- [ ] **Step 2: Implement**
  - Add the filter and its two calls, and the pyproject line.
  - Close every `httpx.AsyncClient` the tests open: `async with`, or a fixture that `aclose()`s (`test_llm.py:109`, `test_sse.py:174`, `test_studio_routes.py:60`).
  - [fell through] Tighten the tool-toggle prompt-record assertions in `test_graph.py` to `rec.role == "agent"`.
  - [fell through] For the Wave 4 renamed-key shape and the two `test_myth.py` nits (a blank line, an in-function import) and the Wave 1 `settings_store` import order: fix whatever is still present. For any already fixed (the renamed-key comment exists at `test_myth.py:70`), record "already done at `<file:line>`" in the issue.

- [ ] **Step 3: Verify the warnings are gone.** Run `cd api && uv run pytest -q -W error::pytest.PytestDeprecationWarning`. Expected: PASS, with no "asyncio_default_fixture_loop_scope" line and no `ResourceWarning` about an unclosed client.

- [ ] **Step 4: Full verification, then commit** with `Refs: #77`, `Closes: #77`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task F (#78): Fable wave review, fixes, push

- [ ] Fable reviews M3 Wave 1 as a whole, over the diff `<wave base>..HEAD`. It also reads design §4.1/§6–§8, this plan and its rulings, and the M2 sources each task cites. Design and pattern adherence come first. It checks:
  - that every §4.1 item and every R1 item is fixed or closed by a written ruling (design §2);
  - the invariants in Global Constraints;
  - the five Review Focus tests.
- [ ] Record the triage table in #78 in both repos. Fixes go in #78 with an Opus 5.5 re-review. Nothing is deferred to "later" without a named M3 wave.
- [ ] Run Full verification, then the security evals once: `cd api && uv run pytest -m eval -k "guard or injection or canary" -v -s`. Task 1 changed the extractor's reply handling and Task 5 changed the guard's retry. Record the numbers in #78. The Pydantic `parsed` warning should be absent from that run's output.
- [ ] Run the exit demo once (`web/e2e`). The thread list and import paths changed underneath it. Copy `test-results/` before any re-run.
- [ ] Push (user delegated 2026-11-09: push after this wave's Fable review fixes land and everything passes; no confirmation needed for this M3 run) `main` to `origin` and `sagaloom`. Update issues #70–#77 and #78 (label `status: done`, ticked criteria, What was done, Commits, Reviews).
- [ ] Copy the ledger and reviews to `internal docs/m3/<YYYY-MM-DD-HHMM>-m3-wave1-*.md`.
