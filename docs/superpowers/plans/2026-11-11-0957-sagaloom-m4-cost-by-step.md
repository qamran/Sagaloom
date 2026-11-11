# Sagaloom M4 (Cost by Step) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every chat turn shows its tokens and cost under its last visible message, and that line expands into a split by step (Guard, Router, Chat, Check, Extraction). Under the hood groups its model calls by step with subtotals. Studio's "Cost by model" becomes "Cost by step".

**Architecture:**
- **Server:**
  - Every displayed message a turn writes carries `additional_kwargs.turn_id`. That is the same id the PromptLog stores as each record's `run_id`. The route creates it before the run and passes it in through `config["configurable"]["turn_id"]`.
  - `GET /api/threads/{id}` returns `turn_id` on each message and a new `turns` list, which holds each turn's usage split by role and is read from the PromptLog.
- **Web:**
  - One role → step map (`web/lib/steps.ts`) serves Studio, the chat cost line and the drawer.
  - `useAgentStream` re-reads the thread after every finished turn, so the messages it holds carry turn ids.
  - The drawer groups the `TurnView.calls` it already has.
- There is no new endpoint and no SSE change.

**Tech Stack:** API: Python 3.12, FastAPI, LangGraph, pydantic, pytest. Web: Next.js 16, React 19, TanStack Query, Tailwind tokens, Vitest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-11-0916-sagaloom-m4-cost-by-step-design.md` (all of it). Mockups: https://claude.ai/artifact/47zGPGb6cvJGYwDJiMRRqQ (options 1 and 2). Requirements: R14.1–R14.3, R16 ruling, R20.3.

> **Line references** are as of the M4 design commit. Re-locate by symbol before editing.

## Global Constraints

- **Step map,** in this fixed display order: `guard`→Guard, `router`→Router, `agent`→Chat, `judge`→Check, `extractor`→Extraction, anything else or null→Other. Show a step only if it has calls.
- **The PromptLog is the only source of usage figures** (Ruling R16). Per-turn totals must equal `promptlog.usage(thread_id, run_id)`.
- **No change to the SSE event set,** and no new endpoint.
- **Link turns to messages only by the stored `turn_id`.** Never by position and never by matching text (like R-W5-7).
- **Displayed message roles** in chat: `user`, `assistant`, `review`, `guard`, `memory`. Only these need `turn_id`. `tool` and `import` don't.
- **Money** is shown as US$ to 4 decimals (`$0.0063`). Tokens are shown as `in → out` with `en-US` grouping and tabular numbers.
- **Colours** come from existing Tailwind tokens only. `web/tests/colorTokens.test.ts` must stay green.
- **Messages from before M4** have no `turn_id`. Every reader must handle that: no cost line and no crash.
- **Commits:** each one carries `Refs #<issue>` or `Closes #<issue>` and ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The issues are #98 (design, plan, Fable review) and #99–#104 (Tasks 1–6), in both repos, under the milestone "M4: cost by step". Push only after the user confirms.
- **Commands:**
  - API: `cd api && uv run pytest -q`
  - Web: `cd web && pnpm vitest run && pnpm lint && pnpm build` (lint can take more than 2 minutes, so give it a long timeout).

## Review Focus

1. **A blocked message.** The guard removes the author's message and leaves its own notice. That notice must carry the turn id, and the line goes under it. Pinned in Task 1, `test_guard_notice_carries_turn_id`, and in Task 4, `cost line under guard notice`.
2. **A turn split by the approval gate.** The chat turn (agent, extractor and judge) pauses. The decision is a second turn (commit, then the agent's reply). That gives two lines, one per turn, and the paused turn's line sits above the approval card. Pinned in Task 1, `test_decision_turn_has_its_own_turn_id`, and in Task 4, `paused turn line renders before the approval card`.
3. **A failed model call.** A record with no response counts as a call and adds 0 tokens and $0. The step and turn totals still equal `usage()`. Pinned in Task 2, `test_usage_by_turn_counts_failed_call`.
4. **An old thread.** Messages without `turn_id`, and a `turns` list that holds log groups with no matching message, render no line and throw nothing. Pinned in Task 4, `no line for messages without turn_id`.
5. **The re-read after a chat turn fails** (network). The streamed messages stay, the status goes to `idle`, and no error banner appears. A decision turn still shows the existing error. Pinned in Task 4, `restore failure after a chat turn keeps messages and goes idle`.

---

### Task 1: Turn ids on displayed messages (API)

**Files:**
- Modify: `api/sagaloom/web/routes.py`: `_turn_config` (~126), `_turn` (~172), `_stream_run` (~191), `post_message` (~448), `post_decisions` (~470), `message_dict` (~90)
- Modify: `api/sagaloom/graph/nodes.py`: add a helper next to `_review` (~74). Stamp in `guard` (~157), `agent` (~216), `remember` (~330) and `commit` (~540)
- Modify, if the import route builds its own config: `api/sagaloom/web/imports.py`. It should go through `_turn`/`_turn_config`, so it gets the id for free.
- Test: `api/tests/web/test_turn_ids.py` (new). Base the scripted turns on the existing route tests that already drive each path: a guard block, a `remember` turn, and a pause followed by a decision (`api/tests/web/test_routes.py`, `test_memory_routes.py` and the guard tests, with `fakes.py` and `conftest.py`). Don't assume the fakes can script a path until you've found a test that does it.

**Interfaces:**
- Produces:
  - `config["configurable"]["turn_id"]: str` on every turn run.
  - `with_turn(msgs: list[BaseMessage], config: RunnableConfig | None) -> list[BaseMessage]` in `nodes.py`. It returns copies with `additional_kwargs["turn_id"]` set when the config has one, and the messages unchanged otherwise.
  - `message_dict(m)` adds `"turn_id": str` whenever `m.additional_kwargs.get("turn_id")` is set, for every message type.
  - `_turn(request, thread, turn_id: str | None = None)` and `_stream_run(request, thread, input_or_command, release, turn_id: str | None = None)`. They use the given id, or else a new `uuid4().hex`.

- [ ] **Step 1: Write the failing tests** in `api/tests/web/test_turn_ids.py`:
  - `test_chat_turn_stamps_user_and_reply`. POST a message on a scripted fake turn whose agent replies with text. Then `GET /threads/{id}`. The user message and the assistant reply carry the same non-empty `turn_id`, and it equals the `run_id` of every PromptLog record of that turn (`promptlog.list(thread_id)`).
  - `test_decision_turn_has_its_own_turn_id`. Script a turn that proposes and pauses, then POST a decision. The review note(s) and the follow-up assistant reply share one `turn_id`. It differs from the first turn's id and equals the decision turn's record `run_id`.
  - `test_guard_notice_carries_turn_id`. Script the guard to block. The `guard` message has the turn's id.
  - `test_memory_note_carries_turn_id`. Script a `remember` turn. The `memory` message has the turn's id.
  - `test_tool_messages_need_no_turn_id`. Tool messages may lack `turn_id`, and `message_dict` still works for them (no `KeyError`).
  - `test_message_without_turn_id_serialises_without_field`. `message_dict(HumanMessage("hi"))` has no `turn_id` key.
- [ ] **Step 2: Run them to check they fail.** Run `cd api && uv run pytest -q tests/web/test_turn_ids.py`. Expected: FAIL (no `turn_id` in the message dicts).
- [ ] **Step 3: Implement.**
  - **In `post_message`:** create `turn_id = uuid.uuid4().hex`, build `HumanMessage(content=..., additional_kwargs={"turn_id": turn_id})` and pass `turn_id=` through `_stream_run` → `_turn`.
  - **In `_turn_config`:** set `cfg["configurable"]["turn_id"] = turn_id`.
  - **In the nodes:** wrap the messages each one returns in `with_turn(..., config)`. That covers the guard's notice, the agent's `reply`, the remember note and every `_review(...)` in `commit`.
  - Add `config: RunnableConfig` to the signatures that lack it. LangGraph injects it into sync and async nodes alike.
  - Don't stamp in `tools_node` or `router`. The router already copies the author's message with `additional_kwargs` kept, so the id survives.
  - **Check:** an AIMessage's extra `additional_kwargs` key must not reach the OpenRouter request body. `mode` on HumanMessage is the precedent, and `langchain_openai` sends only known keys. Assert it in `test_chat_turn_stamps_user_and_reply`: the second turn's recorded request messages don't contain the string `turn_id`, **or** document in the test why they do and why that's harmless. Pick whichever matches what `PromptLogHandler._message` really records.
- [ ] **Step 4: Run the full API suite.** Run `cd api && uv run pytest -q`. Expected: all pass, and the count is the previous 857 plus the new tests.
- [ ] **Step 5: Commit** with `feat(api): stamp turn_id on displayed messages (M4)` and `Refs #99`.

### Task 2: Per-turn usage by role in `GET /threads/{id}` (API)

**Files:**
- Modify: `api/sagaloom/models.py`. Next to `Usage` (~203), add `RoleUsage` and `TurnUsage`.
- Modify: `api/sagaloom/promptlog.py`. Next to `usage()` (~123), add `usage_by_turn`.
- Modify: `api/sagaloom/web/routes.py` `get_thread` (~426). Add `"turns"`.
- Test: `api/tests/test_promptlog.py` (extend) and `api/tests/web/test_routes.py` (extend).

**Interfaces:**
- Produces:
  - `class RoleUsage(BaseModel): role: str | None; calls: int; prompt_tokens: int; completion_tokens: int; cost_usd: float`
  - `class TurnUsage(BaseModel): turn_id: str; usage: Usage; by_role: list[RoleUsage]`
  - `PromptLog.usage_by_turn(self, thread_id: str) -> list[TurnUsage]`. Turns are ordered by their first record's `started_at`, then rowid. `by_role` is in first-seen order (the web reorders it).
  - JSON: `GET /api/threads/{id}` gains `"turns": [TurnUsage.model_dump()]`.

- [ ] **Step 1: Write the failing tests.**
  - `test_usage_by_turn_groups_by_run_and_role`. Two turns. Turn A has agent ×2, judge ×1 and extractor ×1. Turn B has agent ×1. Assert two items in start order, A's `by_role` holds agent `calls == 2` with summed tokens and cost, and each turn's `usage == promptlog.usage(thread_id, run_id)`.
  - `test_usage_by_turn_counts_failed_call`. A judge record with `response=None` gives `calls == 1` with 0 tokens and `cost_usd == 0.0`, and the totals still equal `usage()`.
  - `test_usage_by_turn_null_role`. A record with `role=None` is grouped under `role: None`.
  - `test_usage_by_turn_other_thread_excluded`. Records from another thread don't appear.
  - In `test_routes.py`, `test_get_thread_returns_turns`. After a scripted turn, `turns` has one item whose `turn_id` equals the messages' `turn_id` (from Task 1) and whose `usage` equals the response's per-turn usage.
- [ ] **Step 2: Run them to check they fail.** Run `cd api && uv run pytest -q tests/test_promptlog.py tests/web/test_routes.py -k "usage_by_turn or returns_turns"`. Expected: FAIL (`AttributeError: usage_by_turn`).
- [ ] **Step 3: Implement `usage_by_turn`.** Run one `SELECT record ... WHERE thread_id = ? ORDER BY started_at, rowid`, then aggregate in Python. Use the same response fields and `or 0` handling as `usage()`, so the totals match exactly. Add `"turns": [t.model_dump() for t in promptlog.usage_by_turn(thread_id)]` to `get_thread`.
- [ ] **Step 4: Run the API suite and the types check.** Run `cd api && uv run pytest -q`, then `pnpm types:gen && pnpm types:check` from the root. Expected: all pass. `get_thread` returns a `dict`, so the generated types may not change. If they do, commit them.
- [ ] **Step 5: Commit** with `feat(api): per-turn usage by role on GET /threads/{id} (M4)` and `Refs #100`.

### Task 3: Step map, web types and the Studio rename (web)

**Files:**
- Create: `web/lib/steps.ts`
- Modify: `web/lib/types.ts`. Add `turn_id?: string` to `ChatMessage` (~121), add `turns?: TurnUsage[]` to `ThreadState` (~143), and add `RoleUsage` and `TurnUsage`, hand-written to mirror Task 2.
- Modify: `web/components/UsagePanel.tsx`. `usageLabel` uses the step names, and the heading becomes "Cost by step".
- Test: `web/tests/steps.test.ts` (new) and `web/tests/FeatureMap.test.tsx` (~109–124, update).

**Interfaces:**
- Consumes: Task 2's JSON shape.
- Produces (in `web/lib/steps.ts`):
  - `type StepKey = "guard" | "router" | "chat" | "check" | "extraction" | "other"`
  - `const STEPS: readonly { key: StepKey; name: string; bar: string }[]`. They are in the Global Constraints order. `bar` is a Tailwind background class from existing tokens. Suggested: `bg-rule`, `bg-place`, `bg-accent`, `bg-event`, `bg-faction`, `bg-muted-foreground`.
  - `stepOf(role: string | null | undefined): StepKey`
  - `interface StepTotal { key: StepKey; name: string; bar: string; calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number }`
  - `stepsFromRoles(byRole: RoleUsage[]): StepTotal[]`. It merges roles that map to the same step (for example two unknown roles into Other), drops empty steps and returns them in `STEPS` order.
  - `usageLabel(role, model)` keeps its signature. A known role now reads `"<Step name> (<short model>)"`, for example `"Check (Luna)"`. An unknown or null role still returns the bare `model`, as today.

- [ ] **Step 1: Write the failing tests.**
  - In `steps.test.ts`:
    - `stepOf maps every role`: `judge`→`check`, `agent`→`chat`, `extractor`→`extraction`, `guard`, `router`, and both `null` and `"weird"`→`other`.
    - `stepsFromRoles orders by pipeline not input`: input `[judge, agent, guard]` comes out as Guard, Chat, Check.
    - `stepsFromRoles merges and sums`: two unknown roles give one Other row whose calls, tokens and cost are summed, and the sum of `cost_usd` over the output equals the sum over the input.
    - `stepsFromRoles drops empty input`: `[]` gives `[]`.
  - In `FeatureMap.test.tsx`: assert the heading "Cost by step" and a row label `Check (Luna)` where it used to be `Judge (Luna)`. A row with an unknown role still shows the bare model id, not "Other (Luna)" (spec §3.6).
- [ ] **Step 2: Run them to check they fail.** Run `cd web && pnpm vitest run tests/steps.test.ts tests/FeatureMap.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** `steps.ts`, the types and the `UsagePanel` changes. `ROLE_SHORT` goes away in favour of `STEPS`.
- [ ] **Step 4: Run all web tests.** Run `cd web && pnpm vitest run`. Expected: all pass, including `colorTokens.test.ts` and `apiTypes.test-d.ts`.
- [ ] **Step 5: Commit** with `feat(web): step map and Studio "Cost by step" (M4)` and `Refs #101`.

### Task 4: Cost line under each turn (web)

**Files:**
- Create: `web/components/TurnCost.tsx`
- Modify: `web/lib/useAgentStream.ts`. Expose `turns`, set it in `applyThread` (~156) and `restore()` after every `done` (~305).
- Modify: `web/components/ChatThread.tsx`. Render `TurnCost` after the last displayed message of each turn (the messages map, ~255).
- Test: `web/tests/TurnCost.test.tsx` (new), `web/tests/ChatPage.test.tsx` (extend), `web/tests/useAgentStream.test.tsx` (extend) and `web/tests/ReviewDetail.test.tsx` (must stay green).

**Interfaces:**
- Consumes: `TurnUsage`, `ChatMessage.turn_id`, `stepsFromRoles` and `StepTotal` from Task 3.
- Produces:
  - `useAgentStream(...)` returns `turns: TurnUsage[]`, which is `[]` until loaded.
  - `<TurnCost turn={TurnUsage} />`:
    - It renders nothing when `turn.by_role` has no calls.
    - Collapsed, it's a `<button aria-expanded>` labelled `"{in+out tokens} tokens · ${usd} · {n} step(s)"`.
    - Expanded, it adds a stacked bar (segment widths ∝ step cost, using each `bar` class) and a grid. Each row has the step name, `"{calls} call(s)"`, `"{in} → {out}"` and the US$. The Total row uses `turn.usage`.
  - `SHOWN_ROLES: readonly string[] = ["user", "assistant", "review", "guard", "memory"]`, exported from `web/lib/steps.ts`.

- [ ] **Step 1: Write the failing tests.**
  - `TurnCost.test.tsx`:
    - `collapsed line shows tokens cost and step count`: the fixture turn (guard, router, agent ×2 and judge, as in the mockup) shows `9,211 tokens`, `$0.0063` and `4 steps`. The fixture is guard 612→18 ($0.00041), router 488→12 ($0.00032), agent 1,904→96 ($0.00121), agent 2,310→141 ($0.00156) and judge 3,420→210 ($0.00280).
    - `expands to rows in pipeline order`: clicking flips `aria-expanded` to `"true"`, and the rows read Guard, Router, Chat, Check in that order.
    - `row sums equal the total`: the sum of row costs equals `turn.usage.cost_usd` to 1e-9 (check the data, not the rounded text).
    - `renders nothing for a turn without calls`.
  - `ChatPage.test.tsx`, with a thread fixture carrying `turn_id`s and `turns`:
    - `cost line under the last displayed message of a turn`: a turn whose last message is a `tool` gets its line under the preceding assistant message.
    - `paused turn line renders before the approval card`: in DOM order, the line comes before the first `ApprovalCard`.
    - `cost line under guard notice`.
    - `no line for messages without turn_id`: an old-thread fixture without `turn_id` (and with or without `turns`) has no cost button and no error.
  - `useAgentStream.test.tsx`:
    - `restores the thread after a chat turn ends with done`: `getThread` is called again after `done` on a `kind: "message"` turn, and `turns` updates. The status reaches `idle` only after the restore settles.
    - `restores after a paused turn`: the stream is `interrupt → usage → done`, `getThread` is called again, and `pending` stays set. The server sends `done` after `interrupt` (`api/sagaloom/web/sse.py` ~145–164), so this is the path that gives the paused turn its line.
    - `restore failure after a chat turn keeps messages and goes idle`: `getThread` rejects after `done`, the status is `idle`, there's no error, and the streamed messages are still there.
    - The existing decision-turn restore and error tests must still pass unchanged.
- [ ] **Step 2: Run them to check they fail.** Run `cd web && pnpm vitest run tests/TurnCost.test.tsx tests/ChatPage.test.tsx tests/useAgentStream.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - **In `useAgentStream`:** on `done`, call `restore()` for every kind, then set `idle`. Every kind stays "streaming" until the restore settles. A decision turn keeps its current failure behaviour (`LOST` error). For a `"message"` turn, a failure is swallowed and the status goes to `idle`. Keep the scroll position stable when the messages are swapped.
  - **In `ChatThread`:**
    - build `lastIndexByTurn: Map<string, number>` over messages whose role is in `SHOWN_ROLES` and that have a `turn_id`;
    - build `turnById` from `s.turns`;
    - after the message at that index, render `<TurnCost>` when the turn exists.
  - Expanded state is local to each `TurnCost` (`useState`).
- [ ] **Step 4: Run all web tests.** Run `cd web && pnpm vitest run`. Expected: all pass, including `ReviewDetail.test.tsx` unchanged.
- [ ] **Step 5: Commit** with `feat(web): cost by step under each turn (M4)` and `Refs #102`.

### Task 5: Under the hood grouped by step (web)

**Files:**
- Modify: `web/lib/steps.ts`. Add `groupCalls`.
- Modify: `web/components/UnderTheHood.tsx`. The "Prompts sent to OpenRouter" list (~392) becomes step groups, and `CallCard` stays as it is.
- Test: `web/tests/steps.test.ts` (extend) and `web/tests/UnderTheHood.test.tsx` (extend).

**Interfaces:**
- Consumes: `LlmCall` (`web/lib/turns.ts`), plus `STEPS` and `stepOf` from Task 3.
- Produces: `groupCalls(calls: LlmCall[]): { key: StepKey; name: string; bar: string; items: { call: LlmCall; index: number }[]; calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number }[]`.
  - The groups are in `STEPS` order, and empty groups are dropped.
  - `index` is the call's position in the whole turn.
  - Totals come from `call.response` (a missing response counts as 0).

- [ ] **Step 1: Write the failing tests.**
  - `steps.test.ts`:
    - `groupCalls keeps turn-wide indexes`: calls `[agent, judge, agent]` give Chat items with indexes `[0, 2]` and Check items with `[1]`.
    - `groupCalls counts a call without response as zero`.
  - `UnderTheHood.test.tsx`:
    - `groups calls by step in pipeline order`: the group headings read Guard, Router, Chat, Check.
    - `group header shows calls tokens and cost`: e.g. `"2 calls"`, `"4,214 → 237"` and `"$0.0028"` for the fixture's Chat group.
    - `most expensive group starts open`: only that group's call cards are visible, and a tie opens the earlier group.
    - `cards keep their turn index`: the Check card shows the index it had before grouping.
    - `copy turn as JSON keeps call order`: the copied `calls` are in the original order.
    - Existing secrets-masking tests stay green.
- [ ] **Step 2: Run them to check they fail.** Run `cd web && pnpm vitest run tests/steps.test.ts tests/UnderTheHood.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** `groupCalls`, then a `StepGroup` disclosure in `UnderTheHood.tsx`. Its header is a `<button aria-expanded>` holding the step name with a colour key, `"{n} call(s) · {in} → {out} tok"`, the US$, and a thin share bar (`width = cost / turn total`; 0 when the turn total is 0). It contains the `CallCard`s with their original `index` and `defaultOpen={index === 0}`, as today, using the turn-wide index. So the open group's cards start collapsed unless call #1 is in that group (spec §3.5), and that is intended. The drawer header, graph path, tool calls and copy stay unchanged.
  - **Check the e2e demo's drawer selectors.** `web/e2e` step 7 (~108–113) and ~529 open Under the hood and read the judge's request, and that request now sits inside the Check group, which may start closed. Update the demo to expand the Check group first if needed.
- [ ] **Step 4: Run the full web checks.** Run `cd web && pnpm vitest run && pnpm lint && pnpm build`. Expected: all pass, lint is clean and the build succeeds.
- [ ] **Step 5: Commit** with `feat(web): Under the hood grouped by step (M4)` and `Refs #103`.

### Task 6: Requirements, README and handoff

**Files:**
- Modify: `docs/requirements.md`. Change R14.3 (~394) and add a change-log row.
- Modify: `README.md`, with one feature line.
- Modify: `internal docs/handoff.md`: M4 done, and cost by step removed from the §6.2 backlog.

- [ ] **Step 1:** Update R14.3:
  - Priority: `Should (M4)`.
  - Done when: "Every turn with model calls shows a per-step split (Guard, Router, Chat, Check, Extraction) under its last displayed message that sums to the turn total and survives a refresh; Under the hood groups the turn's calls by step with subtotals; Studio's usage panel reads 'Cost by step'."
  - Add a change-log row dated 2026-11-11 that cites the M4 design.
- [ ] **Step 2:** In `README.md`, add a line under features: "Cost by step: each turn's cost split by Guard, Router, Chat, Check and Extraction, under the reply and in Under the hood."
- [ ] **Step 3:** Run the full suites once more. Run `cd api && uv run pytest -q`, then `cd web && pnpm vitest run`. Then run the Playwright demo once, with the command in the handoff §5. Task 4 changes how every turn ends, and Task 5 changes the drawer the demo clicks into. Expected: all pass. Record the counts in the handoff.
- **Copy note:** Studio's usage panel aggregates every record across all worlds (`usage_by_model` has no filter). The README and handoff call it the "overall" spend, not "per world".
- [ ] **Step 4: Commit** with `docs: R14.3 done, README and handoff for M4` and `Closes #104`.
