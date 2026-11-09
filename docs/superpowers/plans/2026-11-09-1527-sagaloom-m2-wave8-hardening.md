# Sagaloom M2 Wave 8: Hardening, Generated Types, Docs, Final Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every Should "Done when" of M2 is ticked, the deferrals a reviewer could hit are fixed, the docs claim exactly what the code does, and M2 passes a Fable whole-M2 review.

**Architecture:** No new features. The work is: generated web types from the API's OpenAPI schema; a store-level version guard and lock hygiene on the server; robustness fixes on three server paths and the Next proxy; the remaining on-screen secret leaks; flake fixes; docs. The graph gains one conditional edge (`route_after_commit` → `check`), so both Mermaid docs are regenerated.

**Tech Stack:** FastAPI + LangGraph 1.2 + Chroma (api/, `uv`), Next.js 16 + React 19 + vitest 5 (web/, `pnpm`), `openapi-typescript` (new dev dependency), Playwright.

**Spec:** `docs/superpowers/specs/2026-11-05-0947-sagaloom-m2-design.md` §2 Wave 8, §4 F5; deferrals from `internal docs/handoff.md` §6.2 and the Fable review triage tables in `internal docs/m2/`.

## User decisions (2026-11-09)

1. **Cut: Standard.** The spec's work, plus the flakes, three server robustness bugs, and the Wave 7 secret leftovers M2, M9, M10 and M13. Everything else goes to the "Carried to M3" list at the end of this plan.
2. **Types check is a local script** (`pnpm types:check`), run in every verification step and listed in the README. No CI workflow.
3. **Delete card (M2):** entries that name the deleted entry in their text are listed by name. Entries tied to it only by a link are a count ("and 1 linked entry"), and are named only while the world's secrets are shown.
4. **Edit form (M9):** a secret draft opens with its title and body masked, with one **Show to edit** button that reveals them for this card only.

## Global Constraints

- Work goes on `main`. Every commit has `Refs: #N`; the last commit of an issue has `Closes: #N`. End every commit with `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
- Issue numbers in both repos: **#61** plan, **#62–#67** Tasks 1–6, **#68** Fable whole-M2 review fixes. Milestone "M2: bonus tasks and points of difference".
- Never read or print `api/.env` or `web/.env.local`. Never call Gemini. Only models in `api/sagaloom/allowed_models.json`.
- The SSE event set does not change: `token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`.
- The secret rule stays one rule everywhere: hidden when `secret && !worldShown && !locallyRevealed`, where `worldShown` comes from the content's world (`useWorldShowSecrets()`), not the picker's.
- Whenever the compiled graph changes, regenerate the README and `docs/requirements.md` Mermaid diagrams; `api/tests/graph/test_diagram.py` pins them.
- Web vitest runs as `pnpm vitest run --maxWorkers=2` until Task 4 lands, then as `pnpm vitest run` (the config then fixes the worker count and timeout). `pnpm lint` needs a long timeout (more than 2 minutes).
- Verification for every task: `cd api && uv run pytest -q`, `cd web && pnpm vitest run && pnpm lint && pnpm build`, and, from Task 1 on, `pnpm types:check` at the repo root.

## Review Focus

1. **Two approvals of the same entry from two tabs.** The second commit must fail with "entry changed since it was checked", and the store must refuse it even if `_COMMIT_LOCK` is bypassed (Task 2 test `test_upsert_refuses_stale_version`).
2. **A turn cancelled before its first step (tab closed instantly, or shutdown).** The thread's lock must be released, so the next POST is not 409 forever (Task 2 test `test_shielded_releases_when_cancelled_before_start`).
3. **The API is down, or `API_SHARED_SECRET` is empty, while the web app runs.** The proxy answers JSON (502 / 500) that the client's error path can show, not an HTML stack page or a silent 401 loop (Task 3 proxy tests).
4. **Deleting an entry that a secret entry links to, with secrets hidden.** No secret title reaches the delete card, the queue summary or the Edit form (Task 5 tests).
5. **One corrupt checkpoint in a world.** Review, Recent imports and the header pill must still list every other thread (Task 3 test `test_list_threads_skips_unreadable_checkpoint`).

---

### Task 0 (#61): Plan

- [ ] Create issues #61–#68 in both repos, in order, with the body sections Aim / What was done / Success criteria / Status / Reviews / Requirements / Commits and label `status: to do`.
- [ ] Commit this plan: `docs: Wave 8 plan` with `Refs: #61`, `Closes: #61`.

---

### Task 1 (#62): Generated API types (R19.3)

Builder: Sonnet 5.5.

**Files:**
- Create: `api/scripts/export_openapi.py`, `web/lib/openapi.json` (committed), `web/lib/api-types.gen.ts` (committed, generated), `web/tests/apiTypes.test.ts`
- Modify: `web/lib/types.ts`, `web/package.json`, `package.json` (root), `.gitattributes` (mark `web/lib/api-types.gen.ts` and `web/lib/openapi.json` `linguist-generated`, `eol=lf`)

**Interfaces:**
- Produces: `web/lib/api-types.gen.ts` exporting `components` (openapi-typescript output). `types.ts` keeps every exported name it has today; `Entry`, `Fact`, `Link`, `World`, `MentionRef`, `EntryDraft`, `Decision`, `PromptRecord` become `export type X = components["schemas"]["X"]`. Literal unions (`EntryType`, `Status`, `Source`) are re-derived from the generated `Entry` (`Entry["type"]` and so on). Every other type (SSE events, `ThreadSummary`, `StudioData`, settings payloads, everything a `-> dict` route returns) stays hand-written; the comment at the top of `types.ts` says so and why.
- Root scripts: `pnpm types:gen` (runs `cd api && uv run python scripts/export_openapi.py`, then `cd web && pnpm exec openapi-typescript lib/openapi.json -o lib/api-types.gen.ts`); `pnpm types:check` (the same into `$TMP`, then fails with exit 1 and the message `Generated API types are stale: run pnpm types:gen` if either file differs from the committed one).

- [ ] **Step 1:** `export_openapi.py` writes `app.openapi()` from `sagaloom.web.app` as JSON with `indent=2, sort_keys=True` and a trailing newline, to the path given as `argv[1]` (default `../web/lib/openapi.json`). It must not need `.env` (use the app factory the tests use if `app` reads settings on import).
- [ ] **Step 2:** Add `openapi-typescript` (exact version, at least two weeks old) to web devDependencies; add the root scripts; add `lib/api-types.gen.ts` to the eslint ignores; run `pnpm types:gen`.
- [ ] **Step 3:** Write `web/tests/apiTypes.test.ts`: a type-level test (`expectTypeOf`) that `Entry` from `@/lib/types` has `id: string`, `version: number` and `facts: Fact[]`, and that `Status` equals `"canon" | "myth" | "rumour" | "secret"`. It fails until Step 4.
- [ ] **Step 4:** Switch `types.ts` to the re-exports. Fix only the compile errors that come from real drift (for example a field the API marks required). If a generated field is optional where the web relied on it being present, fix the API model (`Field(default_factory=…)` already makes it required in output schemas), not the web.
- [ ] **Step 5:** Drift check: add a field to `World` locally, run `pnpm types:check`, and expect exit 1 with the message; revert and expect exit 0.
- [ ] **Step 6:** Full verification (Global Constraints), then commit with `Refs: #62`, `Closes: #62`.

---

### Task 2 (#63): Store-level version guard, lock pruning, shielded-runner edges (F5)

Builder: **Opus 5.5** (concurrency).

**Files:**
- Modify: `api/sagaloom/store/canon.py` (`upsert_entry`, new `VersionConflictError`), `api/sagaloom/graph/nodes.py` (`_apply_locked`), `api/sagaloom/web/routes.py` (`_take_turn`), `api/sagaloom/web/sse.py` (`shielded`), `api/sagaloom/web/app.py` (`_cancel_turns`)
- Test: `api/tests/store/test_canon.py`, `api/tests/graph/test_graph.py`, `api/tests/web/test_sse.py`, `api/tests/web/test_routes.py`

**Interfaces:**
- Produces: `CanonStore.upsert_entry(entry: Entry, *, expected_version: int | None = None) -> Entry`. `None` keeps today's behaviour (seed, import fixtures). `0` means "must not exist yet". `n` means the stored version must be `n`. A mismatch raises `VersionConflictError(entry_id: str, expected: int, actual: int | None)`, a `ValueError` subclass.
- `_apply_locked` passes `expected_version=0` on create and `current.version` on update. A `VersionConflictError` becomes `_CommitFailed("entry changed since it was checked (v{expected} → v{actual}); propose it again")`.

**Honesty note (put it in the docstring and the README limitation, Task 6):** Chroma has no compare-and-swap, so the guard is still read-then-write inside one process. It moves the check into the store, so every writer gets it, and it narrows the window. `_COMMIT_LOCK` plus "run the API as a single process" is the actual guarantee.

- [ ] **Step 1:** Failing tests: `test_upsert_refuses_stale_version` (stored v2, `expected_version=1` raises `VersionConflictError` with `expected=1, actual=2`, and the stored entry is unchanged); `test_upsert_create_refuses_existing_id` (`expected_version=0` on an existing id raises); `test_upsert_without_expected_version_unchanged`; `test_commit_maps_version_conflict` (the store raises → the review note is "approved, but the commit failed: entry changed since it was checked …", outcome `failed`).
- [ ] **Step 2:** Implement, then run the tests.
- [ ] **Step 3:** Lock pruning. Failing test `test_turn_lock_pruned_after_release`: after a turn finishes, `thread_id not in deps.locks`; a 409 for a concurrent POST still holds. In the `release()` of `_take_turn`, after `lock.release()`, delete `deps.locks[thread_id]` only if it is still this lock (`locks.get(thread_id) is lock`). There are no waiters, because the route 409s instead of waiting. `list_threads` already treats a missing lock as not running.
- [ ] **Step 4:** Shielded edges. Failing tests: `test_shielded_releases_when_cancelled_before_start` (create the shielded stream, cancel the task before the loop yields, await it: `on_finish` was called exactly once); `test_cancel_turns_times_out` (a task that ignores cancellation does not block `_cancel_turns` beyond its timeout); `test_message_route_uses_shielded` (patch `sse.shielded` with a spy and POST a message: the spy was called). Patch the spy where the route looks it up (`sagaloom.web.routes.shielded`, imported by name). The cancel-before-start test also asserts the reader ends (the `_END` sentinel reaches the queue), so an attached reader does not hang. Implement: make `on_finish` idempotent and also call it, then put `_END`, from `task.add_done_callback`; `_cancel_turns(tasks, timeout: float = 5.0)` uses `asyncio.wait(pending, timeout=timeout)` and logs a warning naming the count still running.
- [ ] **Step 5:** Full verification, then commit with `Refs: #63`, `Closes: #63`.

---

### Task 3 (#64): Robustness: thread list, stranded import proposals, proxy

Builder: Sonnet 5.5.

**Files:**
- Modify: `api/sagaloom/web/routes.py` (`list_threads`), `api/sagaloom/graph/nodes.py` (`route_after_commit`), `api/sagaloom/graph/build.py`, `web/app/api/proxy/[...path]/route.ts`, `README.md` and `docs/requirements.md` Mermaid blocks (regenerated)
- Test: `api/tests/web/test_routes.py`, `api/tests/graph/test_graph.py`, `api/tests/graph/test_diagram.py` (already pins; must still pass), `web/tests/proxy.test.ts`

**Interfaces:**
- `route_after_commit(state) -> Literal["agent", "check", "__end__"]`: `"check"` when `entry == "import"` and `pending_proposals` is non-empty (a refused proposal is re-checked and the gate interrupts again); `END` for any other import; `"agent"` for chat (unchanged; the chat agent already reads the refused note).
- `list_threads`: the whole per-thread body (`aget_state`, `_pending`, `_outcomes`, title) sits in one `try`; a thread that raises is skipped with `log.exception("list_threads: unreadable checkpoint %s", thread_id)`; the rest are listed.
- Re-check cost: `check` re-judges a refused proposal (one judge call). A proposal refused for a world mismatch is refused again on every cycle; each cycle needs a human decision, so it never loops on its own. Say both in the docstring.
- Proxy: `API_SHARED_SECRET` unset or empty → `500` JSON `{"detail": "API_SHARED_SECRET is not set on the web server"}`, without calling `fetch`. `fetch` throws → `502` JSON `{"detail": "The API is not reachable"}`. Both use `content-type: application/json`. The path guard becomes `path.some((seg) => [".", ".."].includes(decodeSafe(seg)))` (the `""` entry is dead: Next never passes an empty segment, and the old clause excluded it anyway).

- [ ] **Step 1:** Failing API tests: `test_list_threads_skips_unreadable_checkpoint` (a fake graph whose `aget_state` raises for one of three threads → two rows, status 200); `test_route_after_commit_rechecks_stranded_import` (import, one pending → `"check"`); `test_route_after_commit_import_done` (import, none pending → END); `test_import_refused_proposal_is_asked_again` (graph-level: an import thread resumed with a decision for only one of two proposals ends at a fresh interrupt holding the undecided one, not at END).
- [ ] **Step 2:** Implement; add the edge to the graph; regenerate both Mermaid blocks from `draw_mermaid()`; run `uv run pytest -q`.
- [ ] **Step 3:** Failing web tests in `proxy.test.ts`: `answers 500 JSON when the shared secret is empty` (fetch not called); `answers 502 JSON when the API is unreachable` (fetch rejects with `TypeError("fetch failed")`); `still rejects a dot segment`; `passes a text/event-stream response through unbuffered` (the last open M1 M10 smell: the content type and the streamed chunks arrive unchanged). Implement, then run vitest.
- [ ] **Step 4:** Full verification (including `pnpm types:check`), then commit with `Refs: #64`, `Closes: #64`.

---

### Task 4 (#65): Flakes: vitest under load, canary eval, demo step 33c

Builder: Sonnet 5.5.

**Files:**
- Modify: `web/vitest.config.ts`, `api/tests/fixtures/canary_import.md` (and, only if the fixture change is not enough, `api/tests/eval/test_canary_eval.py`), `web/e2e/exit-demo.spec.ts` (step 33c), `web/tests/ImportPage.test.tsx` (the "keeps the pasted text after a failed import" test)

- [ ] **Step 1:** Vitest: set `testTimeout: 15_000` and `maxWorkers: 2` in `test`. In the ImportPage test, replace the timing-sensitive wait with `await screen.findBy…` on the error text before asserting the textarea value. Verify: `pnpm vitest run` three times in a row at the config defaults, all green, and record the wall times.
- [ ] **Step 2:** Canary. The suite-level asserts ("some run committed the canary", "some chat thread saw it") fail about 3% of invocations because the extractor drops the canary sentence about 3 runs in 10. Fix the fixture, not the asserts: make the canary sentence part of a short standalone paragraph about one named entity (for example "The Gull Market's notice board reads: …"), so the extractor's excerpt for that entity must contain it. Keep `CANARY` byte-identical. Run `uv run pytest -m eval -k canary -v -s` twice; each run must print the canary in the committed body in at least 8/10 runs, along with the existing security lines (10/10 clean, no delete proposal).
- [ ] **Step 3:** Demo 33c. If the model drafts the Mayor change as a create, the step rejects that card and resends the same message once; a second create fails the step with a clear message. Do not loosen what 33c checks on the update card.
- [ ] **Step 4:** Full verification, then commit with `Refs: #65`, `Closes: #65`. (The full exit demo runs in Task 6.)

---

### Task 5 (#66): Secret leftovers: delete card, Edit form, queue summary, token guard (M2, M9, M10, M13)

Builder: **Opus 5.5** (security-sensitive).

**Files:**
- Modify: `api/sagaloom/models.py` (`EntryRef`), `api/sagaloom/check/dependency.py`, `api/sagaloom/store/canon.py` (`find_mentions` returns the reason), `web/components/ApprovalCard.tsx` (delete section and `EditForm`), `web/lib/review.ts` (`proposalSummary`), `web/components/ReviewQueue.tsx`, `web/components/ReviewDetail.tsx`, regenerated `web/lib/openapi.json` and `web/lib/api-types.gen.ts` only if `EntryRef` is in the schema
- Test: `api/tests/check/test_dependency.py`, `web/tests/ApprovalCard.test.tsx`, `web/tests/review.test.ts`, new `web/tests/ReviewQueue.test.tsx`, new `web/tests/colorTokens.test.ts`

**Interfaces:**
- `EntryRef` gains `via: Literal["text", "link"] = "text"`. `dependency_check` returns text mentions first (`via="text"`), then entries tied only by a link (`via="link"`). `find_mentions` keeps its signature for callers; add `find_dependents(world_id, entry) -> list[tuple[Entry, Literal["text","link"]]]` and have `find_mentions` use it.
- Delete card: "These entries mention it:" lists `via="text"` refs as today (a secret dependent entry already renders as a `Secret entry` chip via `dependentSecret`; keep that). Link-only refs: while `worldShown` they are listed after the text refs; otherwise one line `and 1 linked entry` / `and N linked entries`. With text refs absent and link refs hidden, the line reads `1 linked entry depends on it` / `N linked entries depend on it`. "No other entries mention it." only when both are empty.
- Review page provider: `ReviewDetail` wraps the queue and card in `SecretsWorldProvider` for the thread's world (today neither file reads the toggle, so without this `useWorldShowSecrets()` in the queue reads nothing).
- Queue title: the one secret rule applies here too. A secret entry's title shows while the world shows secrets and is `Secret entry` otherwise (this replaces the "always masked" comment at `ReviewQueue.tsx:55`; the queue still has no per-row Show).
- `proposalSummary(p, c, secret, proseSecret)`: the callers' predicates take the toggle into account (Wave 7 M10). In `ReviewQueue`, build `existingSecretOf`/`proseSecretOf` so they return false while `useWorldShowSecrets()` is true; `proposalSummary` itself stays a pure function. The delete line counts all dependents (a number reveals nothing).
- `EditForm` gains a prop `secretEntry: boolean`, passed by `ApprovalCard` (true when `draft.status === "secret"` or the proposal's stored entry is secret; `EditForm` cannot know the latter from `draft`). When `secretEntry && !worldShown`, the Title input and Body textarea render as a disabled placeholder `Secret entry: hidden` plus a **Show to edit** button (`aria-label="Show secret entry to edit"`). Clicking it reveals both for this form instance only. Submitting without revealing sends the draft's original title and body unchanged.

- [ ] **Step 1:** API failing tests: `test_dependency_marks_link_only` (the Mayor links to the Ashen Choir only through a link, so delete-checking ent_0004 gives her `via="link"`); `test_dependency_text_mention_first`. Implement, then `uv run pytest -q`.
- [ ] **Step 2:** Web failing tests: `delete card counts a link-only dependent while secrets are hidden` (no "Mayor" text; "and 1 linked entry"); `delete card names link-only dependents when the world shows secrets`; `edit form masks a secret draft until Show to edit`; `submitting an unrevealed secret edit keeps title and body`; `queue summary unmasks while the world shows secrets` (M10); `queue title follows the world toggle`; `colorTokens.test.ts` (M13): extract NAME from `(bg|text|border|ring|fill|stroke|outline|divide|from|to)-NAME` in class strings and from `var(--color-NAME)` under `web/app`, `web/components` and `web/lib`; skip Tailwind built-ins (palette `^(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}$`, `white|black|transparent|current|inherit`), sizes and weights (`xs|sm|base|lg|xl|\d?xl|left|center|right|…`), numbers, opacity suffixes (`/NN`) and arbitrary `[...]` values; every remaining NAME must be defined as `--color-NAME` in `web/app/globals.css`. Seed the skip list until the test passes on today's tree, then prove it bites: a class `bg-nope` in a fixture string fails it.
- [ ] **Step 3:** Implement and run vitest.
- [ ] **Step 4:** `pnpm types:gen` if the schema changed; full verification; commit with `Refs: #66`, `Closes: #66`.

---

### Task 6 (#67): Docs, Wave 8 demo, evals (R1.4, R17.4, R17.5, R17.6 refresh, R13.5, R18.9)

Builder: Sonnet 5.5.

**Files:**
- Modify: `README.md`, `docs/review-notes.md`, `docs/requirements.md` (tick the Wave 8 rows and add a decision-log line for the four user decisions), `web/e2e/exit-demo.spec.ts`, `web/e2e/README.md`

- [ ] **Step 1: README.**
  - Under the intro: one **positioning** paragraph (R1.4): a continuity editor that checks the author's ideas and never writes canon on its own (contrast: Realmweaver's "It coaches. You create.").
  - New section **How Sagaloom compares** (R17.4): a table of Sagaloom vs Realmweaver, LitMemo and StoryGuard, with rows for fact-level contradiction check, human approval before any write, import with verbatim text, hidden secrets, local data and model choice. Sources: `internal docs/competitor_analysis/` (claims as "not advertised, based on vendor pages", per the requirements' definition of "gap").
  - New section **Your data** (R13.5): canon stays in `api/data/` on your machine; through OpenRouter, prompts go to the pinned provider and are not used for training under OpenRouter's and the providers' terms as configured; Gemini's free tier may let Google use prompts, so it is demo-only and never called.
  - Limitations: add "run the API as a single process" (F5, with the honesty note from Task 2), "Gemini is never called", the delete card's link count, and the Edit form's Show to edit. Remove "M1 and Waves 1 to 5 and 7" in favour of the final M2 scope, and keep Fan wiki = M3.
  - Fix the canary paragraph's misquote (README line ~78 vs the fixture after Task 4), add `pnpm types:check` and `pnpm types:gen` to Tests/Commands, and add the `route_after_commit → check` edge to the Mermaid prose (the block itself was regenerated in Task 3).
- [ ] **Step 2: review-notes.** Refresh §1–§4 so the loop description includes guard → router → agent ⇄ tools → remember → check → gate → commit, with entry points (R17.6 a–d, each with an example from this project). Add §11 "Hardening (Wave 8)": the version guard and its limit, shielded runs, proxy errors, generated types.
- [ ] **Step 3: Demo step 34.** In `exit-demo.spec.ts`, after 33d: with secrets hidden, ask "Delete the Ashen Choir." On the seed the Mayor (`ent_0003`) is the only link-only dependent; text dependents (Sky of Velmar, the Salt Guild, Ister, the Song, Warden Vane, Tomas Reeve, and The Choir Ledger as a `Secret entry` chip) are listed too. Assert the card contains `and 1 linked entry` and does not contain `Elsbeth`; after Show secrets it contains `Mayor Elsbeth Varr`; then **Reject**. Assert text, not layout. Run the full exit demo twice in a row; both must pass. Copy `test-results/` before a re-run; check that ports 8100 and 3100 are free afterwards.
- [ ] **Step 4: Evals.** `cd api && uv run pytest -m eval -v -s` once. Record the results in the issue: guard, router, injection, canary, R4.10 and the three-moons flags.
- [ ] **Step 5:** Full verification, then commit with `Refs: #67`, `Closes: #67`.

---

### Task 7 (#68): Fable wave review and whole-M2 review, fixes, push

- [ ] Fable 5.1 reviews Wave 8 as a whole, then M2 as a whole (spec §1.5): the wave diff is `9ca21c28..HEAD`; the whole-M2 diff is `f7f0a720^..HEAD` (`f7f0a720` is the M2 design commit, the first of M2). It also reads the spec, the requirements and this plan. Design and pattern adherence come first.
- [ ] Record the triage table in #68 (both repos). Fixes go in #68 with an Opus 5.5 re-review; deferrals go to the M3 list.
- [ ] Full verification and the evals' security subset (guard, injection, canary).
- [ ] **Confirm with the user**, then push `main` to `origin` and `sagaloom`. Update issues #61–#68 (label `status: done`, ticked criteria, What was done, Commits, Reviews).
- [ ] Copy the ledger and reviews to `internal docs/m2/<HHMM>-wave8-*.md`, delete the SDD workspace, and update `internal docs/handoff.md` (M2 done; M3 backlog = the list below plus Wave 6).

---

## Carried to M3 (not in Wave 8)

- **Wave 7:** five hex one-offs (M8, now guarded by M13's test); `seed_missing` rule (b) prints nothing (M11); test gaps M12; smells M14 (dated-heading regex twice, `BLOCK_PARTS`, `argsHoldSecret` string args, Response tab relying on the veil, `secrets.tsx` stale `"true"`, listener sets, regex per render, 3-character aliases); four Show buttons on a secret create card; two "Show secret entry" buttons.
- **Wave 5:** U+2028/U+2029/U+0085 in the filename pattern; tidy-ups (`sse_response` `on_close`, duplicated `_first_line`, private `_drain`/`_ev` imports, `_extraction` without `aclosing`, synchronous Chroma lookups per candidate, no `usage` on total extraction failure, `PRAGMA table_info` per connect); UI/test nits (`done` without `thread_id` copy, `role="status"` on a list, "Found 1 candidate", `useImport` stream drop and `ImportProgress` untested, the page-wide `From paste:` e2e check).
- **Wave 4:** header pill reads every checkpoint every 15 s; `setHeld` during render; parallel-collapse `ToolMessage` id; `byId` built twice; `norm`/`CHECK_FAILED_TEXT` into `lib`; test nits.
- **Wave 3:** shared structured-classify retry helper; memory lock map pruning and move to `AppDeps`; `MemoryResult.reason`; stale Undo copy; partial store failure reporting; `GEMINI_MODEL` location; typing `_ask_judge`; `exc.request` in the Gemini mapping; test HTTP clients; `_error_event` 503 test; Pydantic serializer warnings; UI polish.
- **Waves 1–2:** pytest-asyncio loop-scope warning; private guard retry constants; guard log "unknown"; `list_by_role` full scan; repeated settings warning; `routes` importing `TOOL_SPECS`; `PROXY_PREFIX` duplication; Mermaid `tools` label; XFF trust and rate-limiter memory (documented); empty-lookup taint note; Studio "Try it" for the reference tool.
- **M1 M10 smells:** `GET /threads` does one `aget_state` per thread (with the Wave 4 pill item). The rest are done: `_text` duplication, tool names without closures (Wave 2), the `RoleModel` Protocol (Wave 3), the check-failed wording (Wave 4), `token_usage` removed; the dead proxy clause, `AppDeps.locks` pruning and the event-stream proxy test are Tasks 2–3.
- **Already done (dropped):** declarative eval `ent_0012` (Wave 4), Feature map cards (all Live; the Import page's Fan wiki card stays "Coming soon").
