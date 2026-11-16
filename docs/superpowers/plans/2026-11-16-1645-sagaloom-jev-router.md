# Jev Router Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An admin-only Studio switch makes the router node pick the turn's mode with either the existing LLM call (default) or the Jev decision model through OpenRouter, visibly, falling back to the LLM when Jev fails.

**Architecture:** A new `router_engine` developer setting is read on every turn by the router node. A new module `api/sagaloom/decision.py` owns the Jev classifier, its `Choice` question and the recording of its call. The record reaches the existing prompt log and SSE stream through a LangChain custom callback event that `PromptLogHandler` handles, so Under the hood, the live chip and the cost line work through existing paths. A Jev failure reruns the existing LLM `route()` with `fallback_for` metadata, which produces the existing fallback note.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, `langchain-typesafe==0.0.1a3` (`TypeSafeClassifier`, `Choice`); Next.js, React, TypeScript, vitest; Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-11-16-1627-sagaloom-jev-router-design.md` (approved 2026-11-16). Read it before any task.

## Global Constraints

- The default `router_engine` is `"llm"`. With it, behaviour is identical to today: existing tests pass unchanged, apart from fixtures gaining the new field.
- Pin exactly: `langchain-typesafe==0.0.1a3` in `api/pyproject.toml`, installed with `uv add`.
- Jev endpoint: `base_url` = `Settings.openrouter_base_url` with one trailing `/v1` removed (`https://openrouter.ai/api`), `api_key` = `Settings.openrouter_api_key`, model = `Settings.router_decision_model` (env `ROUTER_DECISION_MODEL`, default `"jev-latest"`).
- Jev call: `timeout=10.0` seconds, no retry, async `ainvoke`.
- Jev cost is never estimated: the response has `cost_usd: None` and `priced: False`. It shows as "not priced".
- A Jev problem never blocks a turn. The worst case is today's `mode=None`.
- The OpenRouter key never appears in a record, a log line or an error.
- Chip copy: an LLM decision reads `Router · {mode}` (unchanged). A Jev decision reads `Router · {mode} · Jev {round(confidence*100)}%`.
- After any API model change: run `pnpm types:gen` (repo root) and commit `web/lib/openapi.json` and `web/lib/api-types.gen.ts`. `pnpm types:check` must pass.
- Commits: every commit carries `Refs: #N` for its task's issue (the issue's last commit uses `Closes: #N`) and ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- API tests: `cd api && uv run pytest` (no network). Web tests: `cd web && pnpm vitest run`. Type check: `cd web && pnpm tsc --noEmit`.

## Review Focus

1. **Jev answers with a label outside `brainstorm` / `query` / `edit`, or with no `mode` answer.** It is treated as a Jev failure, and the LLM fallback decides. Test in Task 2.
2. **The Jev call hangs.** It is cut off at 10 s and the LLM decides. Task 2 checks the timeout is passed to the classifier, and Task 3 checks that a timeout error falls back.
3. **`settings.json` holds a bad `router_engine`** (`"JEV"`, `true`, `null`). It reads as `"llm"` without an error, through the per-field strict validation. Test in Task 1.
4. **Recording a Jev call where no prompt-log handler or parent run exists** (the eval calls `classify_mode` directly; unit tests run without callbacks). The classification still returns, and a recording failure never raises. Test in Task 2.
5. **Reloading a chat after a Jev turn.** The chip still reads `Router · query · Jev 94%` from the message stamp, not only from the live stream. Tests in Task 3 (stamp is serialised) and Task 5 (label from a loaded message).

---

### Task 1: The `router_engine` setting, config and dependency

**Files:**
- Modify: `api/sagaloom/settings_store.py` (`DevSettings`, `DevSettingsPatch`, `_no_null_for_required`)
- Modify: `api/sagaloom/config.py` (`Settings.router_decision_model`)
- Modify: `api/pyproject.toml`, `api/uv.lock` (via `uv add "langchain-typesafe==0.0.1a3"`)
- Modify: `api/.env.example` (commented `ROUTER_DECISION_MODEL=jev-latest`)
- Modify: `web/lib/types.ts` (`DevSettings.router_engine: "llm" | "jev"`), `web/lib/openapi.json`, `web/lib/api-types.gen.ts` (regenerated)
- Modify: web test fixtures that spell out the whole settings object: `web/tests/ChatPage.test.tsx`, `web/tests/GuardrailsPanel.test.tsx`, `web/tests/SettingsPanel.test.tsx`, plus any others `pnpm tsc --noEmit` flags
- Test: `api/tests/test_settings_store.py`, `api/tests/web/test_settings_routes.py`

**Interfaces:**
- Produces: `DevSettings.router_engine: Literal["llm", "jev"] = "llm"`; `DevSettingsPatch.router_engine: Literal["llm", "jev"] | None = None` (null rejected); `Settings.router_decision_model: str = "jev-latest"`; web `DevSettings.router_engine`.

- [ ] **Step 1: Write the failing tests.** In `test_settings_store.py`:
  - `test_router_engine_defaults_to_llm`: `DevSettings().router_engine == "llm"`.
  - `test_router_engine_round_trips`: `store.update(DevSettingsPatch(router_engine="jev"))` then `store.get().router_engine == "jev"`.
  - `test_bad_router_engine_in_file_reads_as_llm`: parametrised over `"JEV"`, `True`, `None`. Write `{"router_engine": value}` to the settings file; `store.get().router_engine == "llm"`.

  In `test_settings_routes.py`:
  - `test_put_router_engine`: an admin PUT of `{"router_engine": "jev"}` → 200, and GET returns `"jev"`.
  - `test_put_router_engine_rejects_bad_and_null`: `{"router_engine": "gpt"}` → 422; `{"router_engine": null}` → 422.
  - `test_put_router_engine_non_admin_403`.
- [ ] **Step 2: Run them.** `cd api && uv run pytest tests/test_settings_store.py tests/web/test_settings_routes.py -k router_engine -v` → FAIL (unknown field).
- [ ] **Step 3: Implement.**
  - Add the fields above and `"router_engine"` to the `_no_null_for_required` tuple.
  - Add `router_decision_model` to `Settings` beside `guard_model`.
  - Run `cd api && uv add "langchain-typesafe==0.0.1a3"`.
  - Document `ROUTER_DECISION_MODEL` in `.env.example`.
- [ ] **Step 4: Run them.** The same command → PASS. Then `uv run pytest` → all pass.
- [ ] **Step 5: Regenerate types and fix the web fixtures.**
  - Run `pnpm types:gen` (repo root) and add `router_engine` to the web `DevSettings` and to every full-settings fixture.
  - `cd web && pnpm tsc --noEmit && pnpm vitest run` → pass.
  - `pnpm types:check` → pass.
- [ ] **Step 6: Commit.** `feat: router_engine developer setting (llm default) and pinned langchain-typesafe`

### Task 2: `decision.py`: the Jev classifier, its question, and recording its call

**Files:**
- Create: `api/sagaloom/decision.py`
- Modify: `api/sagaloom/promptlog.py` (`PromptLogHandler.on_custom_event`)
- Test: `api/tests/test_decision.py` (create), `api/tests/test_promptlog.py`

**Interfaces:**
- Consumes: `Settings.router_decision_model`, `Settings.openrouter_base_url`, `Settings.openrouter_api_key` (Task 1); `router_mod.MODE_SECTIONS` keys as the valid modes.
- Produces:
  - `decision_base_url(openrouter_base_url: str) -> str`: strips one trailing `/v1` (and a trailing `/`).
  - `make_router_classifier(settings: Settings) -> TypeSafeClassifier`: `timeout=10.0`.
  - `ROUTER_QUESTION: Choice`: `instructions` and three `criteria` keyed `brainstorm`, `query` and `edit`, worded from `router.ROUTER_PROMPT`'s mode descriptions.
  - `class JevDecision(BaseModel)`: `mode: Mode`, `confidence: float`, `model: str`.
  - `class DecisionFailed(Exception)`: an unusable Jev answer.
  - `async def classify_mode(classifier: Any, text: str, *, config: RunnableConfig | None = None) -> JevDecision`. It sends `{"state": text, "questions": {"mode": ROUTER_QUESTION}}` and raises `DecisionFailed` when the `mode` answer is missing or its choice is not a valid mode. It lets classifier exceptions propagate. On success **and** on failure it records the call (see the next bullet) before returning or raising.
  - `DECISION_EVENT = "decision_call"`. The custom event's payload is a dict with:
    - `id` (new uuid hex), `role: "router"`, `provider: "openrouter"`;
    - `model` (the response's `model`, else the classifier's model id);
    - `params: {"engine": "jev", "timeout": 10.0}`;
    - `request: {"messages": [{"role": "user", "content": text}], "tools": [], "question": <ROUTER_QUESTION as a dict>}`;
    - `response: {"content": json.dumps({"mode", "confidence", "engine": "jev"}), "tool_calls": [], "prompt_tokens", "completion_tokens", "cost_usd": None, "priced": False, "latency_ms"}`, plus `error: failure_line(exc)` and zero tokens on failure.

    It is sent with `langchain_core.callbacks.adispatch_custom_event(DECISION_EVENT, payload, config=config)`, wrapped so that any exception (no handler, no parent run) is logged at debug level and swallowed.
  - `PromptLogHandler.on_custom_event(name, data, *, run_id, **kwargs)`: for `name == DECISION_EVENT`, it builds a `PromptRecord` from the payload, with `thread_id`, `run_id=self.turn_id` and `started_at` from the handler as in `on_chat_model_start`, and all fields through `self._clean`. It then calls `log.add` and `log.complete`, and emits `llm_request` followed by `llm_response` in the same shapes `on_chat_model_start` and `on_llm_end` emit. Other names are ignored.

- [ ] **Step 1: Write the failing tests** in `test_decision.py`. Use a fake classifier with `async ainvoke(input, config=None)` that returns or raises a scripted value. Build `ClassifierResponse` objects from the package's types.
  - `test_base_url_strips_v1`: `"https://openrouter.ai/api/v1"` → `"https://openrouter.ai/api"`; `"https://openrouter.ai/api/v1/"` → `"https://openrouter.ai/api"`; `"https://openrouter.ai/api"` is unchanged.
  - `test_make_router_classifier_uses_settings`: the classifier's `model == "jev-latest"`, its base URL is the stripped one, its timeout is `10.0`, and `repr(classifier)` does not contain the key.
  - `test_question_has_three_modes`: `set(ROUTER_QUESTION.criteria) == {"brainstorm", "query", "edit"}`.
  - `test_classify_returns_mode_and_confidence`: the fake answers `query` at 0.94 → `JevDecision(mode="query", confidence=0.94, model=…)`, and the fake received the message text as `state`.
  - `test_unknown_label_raises`: the choice is `"other"` → `DecisionFailed`.
  - `test_missing_answer_raises`: no `mode` key → `DecisionFailed`.
  - `test_records_without_handler_do_not_raise`: `classify_mode(fake, "x")` with no config succeeds.

  In `test_promptlog.py`, add:
  - `test_decision_event_recorded_and_emitted`: dispatch through a real handler inside a run (for example a `RunnableLambda` invoked with `{"callbacks": [handler]}` that calls `classify_mode`). Assert:
    - one record with `role == "router"`, `params["engine"] == "jev"`, `response["cost_usd"] is None` and `response["priced"] is False`;
    - emits `llm_request` then `llm_response` with the same id;
    - `json.loads(response["content"])["mode"] == "query"`.
  - `test_decision_failure_recorded_with_error`: same setup, but the classifier raises, so the record carries `error` and 0 tokens, and the exception reaches the caller.
- [ ] **Step 2: Run them.** `cd api && uv run pytest tests/test_decision.py tests/test_promptlog.py -k "decision or base_url or router_classifier or question or classify or label or missing or handler" -v` → FAIL (no module).
- [ ] **Step 3: Implement** `decision.py` and `on_custom_event` to the interfaces above. Use `failure_line` from `sagaloom.model_errors` for `error`.
- [ ] **Step 4: Run them.** The same command → PASS. Then `uv run pytest` → all pass.
- [ ] **Step 5: Commit.** `feat: Jev decision-model classifier for the router, recorded in the prompt log as an unpriced call`

### Task 3: The router node switches engine and falls back to the LLM

**Files:**
- Modify: `api/sagaloom/router.py` (`route(..., config=None)`)
- Modify: `api/sagaloom/structured.py` (`ask_structured(..., config=None)` passes it to `structured.ainvoke(messages, config)`)
- Modify: `api/sagaloom/graph/nodes.py` (`make_router_node`)
- Modify: `api/sagaloom/graph/build.py` (`build_graph(..., router_classifier=None)`)
- Modify: `api/sagaloom/web/app.py` (build one classifier at startup with `make_router_classifier(settings)` and pass it in; a field on the deps dataclass so tests can inject one)
- Modify: `api/sagaloom/web/routes.py` (copy `router_engine` and `router_confidence` from a user message's `additional_kwargs`)
- Modify: `api/sagaloom/models.py` (if the thread payload's message model is typed there: optional `router_engine: str | None`, `router_confidence: float | None`)
- Test: `api/tests/graph/test_graph.py` (router section), `api/tests/test_router.py`, `api/tests/test_structured.py`, `api/tests/web/test_routes.py`

**Interfaces:**
- Consumes: `classify_mode`, `JevDecision`, `DecisionFailed` (Task 2); `DevSettings.router_engine` (Task 1).
- Produces:
  - `make_router_node(model_for: ModelFor, dev: Callable[[], DevSettings] = DevSettings, classifier: Any | None = None)`. The node takes `config: RunnableConfig | None`.
  - The user-message stamp gains `additional_kwargs["router_engine"]` (`"llm"` or `"jev"`) and, for Jev, `additional_kwargs["router_confidence"]: float`.
  - The thread payload's user messages gain `router_engine?` and `router_confidence?`.
- Behaviour:
  - When `dev().router_engine == "jev"` and `classifier` is not None, the node calls `classify_mode(classifier, text, config=config)`.
  - On any exception, it logs a warning and calls `route(model_for("router"), text, config=<config with metadata {"fallback_for": <the classifier's model id>, "fallback_reason": failure_line(exc)}>)`. The stamped engine is then `"llm"`.
  - When the LLM also fails, it returns `{"mode": None}` as today.
  - `"jev"` with `classifier is None` behaves as `"llm"`.

- [ ] **Step 1: Write the failing tests.**
  - `test_structured.py`, `test_config_reaches_the_model`: the stub's `ainvoke` receives the passed config.
  - `test_graph.py`, using `make(..., dev=lambda: DevSettings(router_engine="jev"), router_classifier=<fake>)`. Extend the `make` helper to pass `router_classifier`.
    - `test_jev_engine_sets_mode_and_stamps_confidence`: the fake answers `edit` at 0.97 → state `mode == "edit"`; the user message has `router_engine == "jev"` and `router_confidence == 0.97`; the scripted LLM router was not called.
    - `test_jev_failure_falls_back_to_llm_with_note`: the fake raises `TimeoutError` and `scripted_router("query")` answers → `mode == "query"`, stamp `router_engine == "llm"`, and the LLM router's received config metadata has `fallback_for == "jev-latest"` and a `fallback_reason` containing `TimeoutError`.
    - `test_jev_and_llm_both_fail_runs_without_mode`: both raise → `mode is None`, and the turn reaches the agent.
    - `test_llm_engine_is_default_and_unchanged`: no dev override → the classifier is not called, and the stamp has `router_engine == "llm"` with no confidence.
  - `test_routes.py`, `test_thread_payload_carries_router_engine`: a user message stamped with engine `jev` and confidence 0.94 serialises both fields.
- [ ] **Step 2: Run them.** `cd api && uv run pytest tests/graph/test_graph.py tests/test_structured.py tests/web/test_routes.py -k "jev or config_reaches or router_engine or llm_engine" -v` → FAIL.
- [ ] **Step 3: Implement** to the interfaces above. Keep `route()`'s untrusted wrapping and retry behaviour unchanged.
- [ ] **Step 4: Run them.** The same command → PASS. Then `uv run pytest` → all pass, including every existing router test unchanged.
- [ ] **Step 5:** `pnpm types:gen` if the API models changed; `pnpm types:check` → pass.
- [ ] **Step 6: Commit.** `feat: router node uses Jev when switched on, falling back to the LLM router visibly`

### Task 4: Usage marks unpriced calls; the Feature map names the engine

**Files:**
- Modify: `api/sagaloom/models.py` (`RoleUsage.unpriced_calls: int = 0`)
- Modify: `api/sagaloom/promptlog.py` (`usage_by_turn` and `usage_by_model` count `unpriced_calls`: records whose response has `priced is False` and `prompt_tokens + completion_tokens > 0`)
- Modify: `api/sagaloom/studio.py` (router card detail)
- Modify: `web/lib/types.ts`, regenerated types
- Test: `api/tests/test_promptlog.py`, `api/tests/test_studio.py`

**Interfaces:**
- Produces:
  - `RoleUsage.unpriced_calls`, and the same key in each `usage_by_model` row.
  - The router card's detail ends with `" Engine: LLM (the input guard's model)."` or `" Engine: Jev decision model ({settings.router_decision_model})."`, following `DevSettings.router_engine`. The status stays `"live"`.

- [ ] **Step 1: Write the failing tests.**
  - `test_unpriced_calls_counted`: a turn with one priced router call and one unpriced Jev call with tokens → the router `RoleUsage` has `unpriced_calls == 1` and `cost_usd` equal to the priced call's.
  - `test_failed_jev_call_not_counted_unpriced`: a Jev record with an error and 0 tokens → `unpriced_calls == 0`.
  - `test_router_card_names_engine`: the card detail contains `Engine: LLM` by default, and `Engine: Jev decision model (jev-latest)` after `DevSettingsPatch(router_engine="jev")`.
- [ ] **Step 2: Run them.** `cd api && uv run pytest tests/test_promptlog.py tests/test_studio.py -k "unpriced or names_engine" -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them** → PASS. Then `uv run pytest` → all pass. Run `pnpm types:gen`, then `pnpm types:check` → pass.
- [ ] **Step 5: Commit.** `feat: unpriced decision-model calls counted per step; Feature map names the router engine`

### Task 5: Web: chip label, live parsing, "not priced" and the Under the hood label

**Files:**
- Modify: `web/lib/types.ts` (`ChatMessage`/`Message`: `router_engine?: "llm" | "jev"`, `router_confidence?: number`; `LlmResponse.priced?: boolean`; `RoleUsage.unpriced_calls?: number`)
- Modify: `web/lib/turns.ts` (`parseRouterMode`)
- Modify: `web/lib/useAgentStream.ts` (`withMode`)
- Create: `web/lib/routerChip.ts` (`routerChipLabel`)
- Modify: `web/components/ChatThread.tsx`, `web/components/TurnCost.tsx`, `web/components/UnderTheHood.tsx`, `web/components/UsagePanel.tsx` (a row with `unpriced_calls > 0` shows `+ not priced` after its cost; test `usage row not priced` in `web/tests/UsagePanel.test.tsx` or the Studio test that renders it)
- Modify: `web/e2e/exit-demo.spec.ts:347-349`
- Test: `web/tests/turns.test.ts` (or the existing parse test file), `web/tests/routerChip.test.ts` (create), `web/tests/ChatPage.test.tsx`, `web/tests/TurnCost.test.tsx`, `web/tests/UnderTheHood.test.tsx`

**Interfaces:**
- Consumes: the API shapes from Tasks 2–4.
- Produces:
  - `parseRouterMode(data: unknown): { mode: Mode; engine: "llm" | "jev"; confidence: number | null } | null`. `engine` is `"jev"` only when the parsed object says so. Update all callers.
  - `routerChipLabel(mode: Mode, engine?: "llm" | "jev", confidence?: number | null): string`: `"Router · query"`, or `"Router · query · Jev 94%"` when the engine is `"jev"` and the confidence is a number.
  - `withMode(msgs, decision)` sets `mode`, `router_engine` and `router_confidence`.

- [ ] **Step 1: Write the failing tests.**
  - `routerChip.test.ts`:
    - `("query")` → `"Router · query"`;
    - `("query", "llm", null)` → `"Router · query"`;
    - `("edit", "jev", 0.966)` → `"Router · edit · Jev 97%"`;
    - `("edit", "jev", null)` → `"Router · edit"`.
  - `parseRouterMode`:
    - JSON content `{"mode":"query","confidence":0.94,"engine":"jev"}` → `{mode:"query", engine:"jev", confidence:0.94}`;
    - an LLM tool-call answer → `{engine:"llm", confidence:null}`;
    - prose → `null`.
  - `ChatPage.test.tsx`, `chip shows Jev confidence after reload`: a loaded user message with `mode:"query", router_engine:"jev", router_confidence:0.94` renders the link named `Course note: Router · query · Jev 94%`. The existing `Course note: Router · query` test still passes.
  - `TurnCost.test.tsx`:
    - `router step not priced`: a turn whose router `by_role` has `unpriced_calls: 1` shows `not priced` on the Router step;
    - the total line includes `(excludes 1 unpriced call)`.
  - `UnderTheHood.test.tsx`, `decision model call`: a router call with `params.engine === "jev"` and `response.priced === false` shows `Router · Decision model (Jev)` and `not priced` instead of a dollar figure.
- [ ] **Step 2: Run them.** `cd web && pnpm vitest run tests/routerChip.test.ts tests/ChatPage.test.tsx tests/TurnCost.test.tsx tests/UnderTheHood.test.tsx` plus the parse test file → FAIL.
- [ ] **Step 3: Implement.**
  - `ChatThread` uses `routerChipLabel(m.mode, m.router_engine, m.router_confidence)`.
  - `TurnCost` shows `not priced` for a step whose `unpriced_calls > 0` and whose `cost_usd` is 0. A step with both priced and unpriced calls shows its dollar figure followed by `+ not priced`. The total gets the excludes suffix.
  - Widen the e2e regex to `/^Course note: Router · (brainstorm|query|edit)( · Jev \d+%)?$/`, and make the `.replace` extract only the mode (for example with a match group).
- [ ] **Step 4: Run them** → PASS. Then `pnpm vitest run && pnpm tsc --noEmit` → pass.
- [ ] **Step 5: Commit.** `feat: router chip, Under the hood and cost line show the Jev decision model and its unpriced calls`

### Task 6: Web: the Router engine switch in Studio

**Files:**
- Create: `web/components/RouterEnginePanel.tsx`
- Modify: `web/app/studio/page.tsx` (render it directly under `<AgentGraph …/>`, with `payload={dev.data}` and `readOnly={readOnly}`)
- Test: `web/tests/RouterEnginePanel.test.tsx` (create), `web/tests/StudioPage.test.tsx`

**Interfaces:**
- Consumes: `putSettings` (`web/lib/api.ts`), the settings payload type `SettingsPanel` uses, and `AdminOnlyNote`. Follow `GuardrailsPanel.tsx`'s toggle pattern (state from the payload, invalidate `["settings"]` exact and `["studio"]`, an error line).
- Produces: `RouterEnginePanel({ payload, readOnly }: { payload: <settings payload type>; readOnly: boolean })`. It renders a radio group named `Router engine` with options `LLM (default)` and `Jev decision model`. One line of help text: "Jev answers one typed question (brainstorm, query or edit) with a confidence, instead of a prompt to a chat model. If Jev fails, the LLM decides that turn." The error copy is "The router engine was not saved. Try again."

- [ ] **Step 1: Write the failing tests.**
  - `shows current engine`: a payload with `router_engine:"jev"` has `Jev decision model` checked.
  - `switching calls putSettings`: choosing LLM calls `putSettings({router_engine:"llm"})`.
  - `read-only disables and shows admin note`.
  - `save failure shows error`.
  - `StudioPage.test.tsx`: the panel renders in Studio.
- [ ] **Step 2: Run them.** `cd web && pnpm vitest run tests/RouterEnginePanel.test.tsx tests/StudioPage.test.tsx` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them** → PASS. Then `pnpm vitest run && pnpm tsc --noEmit` → pass.
- [ ] **Step 5: Commit.** `feat: Studio switch for the router engine (LLM or Jev)`

### Task 7: Eval for both engines, and documentation

**Files:**
- Modify: `api/tests/eval/test_router_eval.py` (parametrise over `"llm"` and `"jev"`; the `"jev"` case calls `classify_mode(make_router_classifier(Settings()), text)`; each needs `MIN_CORRECT = 13`; print the engine, model, confidence and per-message latency)
- Modify: `README.md`:
  - Models: a paragraph on the router engine, the Jev endpoint and "not priced";
  - Your data: router text goes to OpenRouter and on to TypeSafe when Jev is on;
  - walkthrough 12: the switch and the chip suffix;
  - the Course bonus table or reviewer's tour, where the router is named.
- Modify: `docs/requirements.md` (add R6.6 under R6.5: "An admin can switch the router between the LLM and a decision model (Jev); the default is the LLM", Should, Course (Sprint 1 review feedback), acceptance: "Jev picks the right mode for at least 13 of the 15 labelled messages; a Jev failure falls back to the LLM router visibly")
- Modify: `docs/2026-11-11-1541-sprint3-evaluation.md` (Extras table row; the eval result in "Automated proof")

- [ ] **Step 1:** Write the parametrised eval.
- [ ] **Step 2: Run it.** `cd api && uv run pytest -m eval tests/eval/test_router_eval.py -v -s` → both engines PASS (at least 13/15). Record the counts, the Jev model id and the average latency.
- [ ] **Step 3:** Update the three documents with the recorded numbers. Copy follows the README's style: plain sentences, no claims beyond what was run.
- [ ] **Step 4: Manual check.**
  1. Run `pnpm dev`, then in Studio choose `Jev decision model` and send "Give me three ideas for a festival in Velmar." → the chip reads `Router · brainstorm · Jev nn%`.
  2. Under the hood shows the decision-model record with "not priced".
  3. Set `ROUTER_DECISION_MODEL=jev-nonexistent`, restart and send again → the cost line shows "Router: jev-nonexistent failed (…), so the fallback model … answered." Then restore it.
- [ ] **Step 5: Commit.** `docs: router engine (R6.6), Jev eval results` with `Closes: #N`
