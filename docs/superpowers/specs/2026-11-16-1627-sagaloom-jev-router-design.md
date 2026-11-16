# Sagaloom: Jev decision model as a switchable router engine — design

**Date:** 2026-11-16
**Requirement:** R6.6 (new, Should): an admin can switch the router between the LLM and a decision model (Jev); the default is the LLM.

## Why

The Sprint 1 reviewer suggested using Jev, a decision model, instead of an LLM wherever a step only produces a decision. Sagaloom's `router` node is exactly that: one structured-output LLM call whose only output is `brainstorm`, `query` or `edit`. This change lets the author show the reviewer that the suggestion was taken up, side by side with the existing LLM router, so the change must be **visible** in the app, not just a silent swap.

## What was verified before this design (2026-11-16, scratch environment, nothing committed)

- `langchain-typesafe==0.0.1a3` (`TypeSafeClassifier`, marked beta) works with the project's **existing OpenRouter key**: `base_url="https://openrouter.ai/api"`, `model="jev-latest"`. The classifier POSTs to `{base_url}/v1/systemone`. `base_url=".../api/v1"` gives 404, and `typesafe/jev-latest` gives 400 "does not exist". `jev-latest`, `jev-1.13` and `jev-1.14` are on the Turing College tracker allowlist (`internal docs/openrouter_models.md`).
- The 15 labelled messages of `api/tests/eval/test_router_eval.py` with one `Choice` question (criteria written from `ROUTER_PROMPT`): **15/15 correct**, confidence 0.89–1.00, about 0.34 s per call, about 470 input / 40 output tokens per call. The response reports `model: "typesafe/jev-1.14-20261014"` and `usage`, and `request_id` is `None`.
- **OpenRouter publishes no price for Jev**: its public catalogue lists `typesafe/jev-router` with prompt and completion price `-1`.

## Goals

1. A new admin-only developer setting, `router_engine`: `"llm"` (default) or `"jev"`. It is read on every turn, so a switch applies from the next turn, like `guard_enabled`.
2. With `"jev"`, the router node classifies the latest user message with a Jev `Choice` and sets `mode` exactly as today. Everything downstream (mode sections in the agent prompt, `ROUTER_ADVISORY`) is unchanged.
3. With `"llm"`, behaviour is identical to today.
4. If the Jev call fails for any reason (HTTP error, timeout, invalid response), the router falls back to the LLM router for that turn, visibly: the turn shows the existing fallback note, and Under the hood keeps both calls. If the LLM then also fails, the turn runs without a mode, as today.
5. Visible everywhere the router is visible today:
   - **Course chip:** an LLM decision keeps today's label, `Router · query`. A Jev decision reads `Router · query · Jev 94%`, the confidence as a whole percent.
   - **Under the hood:** the Jev call appears as a Router record showing the engine (decision model), the model id Jev reported, the mode, the confidence, tokens, latency and "not priced".
   - **Turn cost line:** the Router step shows its tokens and "not priced" instead of a dollar figure when its call was Jev. Totals add only priced calls, and say so when a Jev call was left out.
   - **Studio Feature map:** the router card's detail names the active engine.
   - **Studio switch:** a "Router engine" control with two options, *LLM (default)* and *Jev decision model*. It is disabled for non-admins, with the existing admin-only note.
6. An eval proves Jev meets the same bar: `test_router_eval.py` runs for both engines, each needing at least 13 of 15.
7. Docs updated: README (Models, Your data, walkthrough 12, Course bonus table where relevant), `docs/requirements.md` (R6.6), the evaluation doc, and `api/.env.example`.

## Non-goals

- The input guard, judge, extractor and agent stay on LLMs. Jev for the guard is a possible later step and is not part of this.
- No per-user switch; the setting is app-wide like every developer setting.
- Jev does not join the per-role model dropdowns or `allowed_models.json` (that list is chat models with prices).
- No confidence threshold. Every measured confidence was 0.89 or above, and a wrong mode is low-harm because tools stay bound in every mode. *(Designer's call; see "Calls made".)*

## Anti-goals (a failure even if it works)

- **The default path changes behaviour.** With `router_engine="llm"` every existing test must pass unchanged, apart from fixtures gaining the new settings field.
- **A Jev problem blocks or breaks a turn.** Jev must never fail closed; the worst case is today's "no mode".
- **A made-up price.** Jev's cost is never estimated from the flat `price_in_per_mtok` / `price_out_per_mtok` defaults or any other guess. It is "not priced" until OpenRouter reports a cost.
- **The key is logged.** The OpenRouter key is passed as a secret and never appears in records, logs or errors (the package already keeps bodies and headers out of `str`/`repr`).

## Constraints

- Python 3.12, uv. Pin the alpha package exactly: `langchain-typesafe==0.0.1a3`. It brings in `httpx2`.
- Base URL: `config.py` has `openrouter_base_url = "https://openrouter.ai/api/v1"`. The classifier needs the same host **without** the trailing `/v1`. Derive it from `openrouter_base_url` (strip one trailing `/v1`) rather than adding a second URL setting.
- The model id is a setting, `ROUTER_DECISION_MODEL` (default `jev-latest`), with the other model settings in `config.py`.
- One long-lived classifier instance per app (connection pooling), built next to `make_model_for` in `api/sagaloom/web/app.py` and passed into `make_router_node`, as the chat models are. Tests inject a fake.
- The project's rules still hold: after an API model change run `pnpm types:gen` and commit `web/lib/openapi.json` and `web/lib/api-types.gen.ts`; `pnpm types:check` must pass.

## How it fits the existing code (from a code survey)

- **Setting.** Add `router_engine: Literal["llm", "jev"] = "llm"` to `DevSettings` and `DevSettingsPatch` (`api/sagaloom/settings_store.py`), and to `_no_null_for_required`. `PUT /api/settings` is already admin-only. Add the field to `DevSettings` in `web/lib/types.ts` and to every web test fixture that spells out the whole settings object.
- **Router node.** `make_router_node(model_for)` gains `dev: Callable[[], DevSettings]` (the guard node's pattern) and the classifier. In `router.py`, add a Jev classification beside `route()` that returns the mode and the confidence. The Jev `Choice` uses `ROUTER_PROMPT`'s descriptions as criteria. The state sent to Jev is the user's message text: there is no instruction channel to inject into, so `wrap_untrusted` is not needed for Jev (designer's call).
- **Message stamp.** Today the node stamps `additional_kwargs["mode"]` on the user message, and `routes.py` copies it out for reloads. Add `router_engine` and, for Jev, `router_confidence` the same way, so the chip survives a reload. Extend the web `Message` type to match.
- **Live chip.** The chip appears live only because `useAgentStream` parses the `llm_response` of a `role == "router"` call (`parseRouterMode` in `web/lib/turns.ts`). So the Jev call must produce the same `llm_request` / `llm_response` events, with `content` the JSON `{"mode": …, "confidence": …, "engine": "jev"}`. Extend `parseRouterMode` to read `engine` and `confidence`.
- **Recording.** `PromptLogHandler` records only chat-model callbacks, so a Jev call is not recorded on its own. It must be recorded through the turn's handler as a `PromptRecord` with:
  - `role "router"`, `provider "openrouter"`, `model` as Jev reported it;
  - a `request` holding the question, its criteria and the message;
  - a `response` with `content` (above), `prompt_tokens`, `completion_tokens`, `cost_usd: null`, `latency_ms`, and `error` on failure;
  - the same SSE events as an LLM call.

  The mechanism is the builder's choice, but it must go through the existing handler and log, not a second log. One option is a LangChain custom callback event handled by `PromptLogHandler`.
- **Unknown price.** Aggregates already treat a null `cost_usd` as 0, which is correct for totals and the budget. The display must not show `$0.0000` for a Jev call:
  - add an explicit marker (for example `priced: false` on the response, surfaced through `RoleUsage` / the turn usage and the call in `turns.ts`);
  - render "not priced" in `TurnCost.tsx`, `UnderTheHood.tsx` and Studio usage, wherever a router cost shows.
- **Fallback.** Reuse the existing fallback note: the LLM router call made after a Jev failure carries `fallback_for = <the Jev model id>` and `fallback_reason = failure_line(exc)` in its record metadata. Then `usage_by_turn` produces a `FallbackUse` and `TurnCost.tsx` shows "Router: jev-latest failed (…), so the fallback model … answered." with no new UI.
- **Studio.**
  - The switch goes in the Agent graph panel, beside the drawing of the router node it changes. It follows `GuardrailsPanel`'s toggle pattern: `putSettings({router_engine})`, invalidate `["settings"]` and `["studio"]`, an error line if saving fails, and `readOnly` plus `AdminOnlyNote`.
  - `build_feature_map` reads the setting and states the engine in the router card's detail. The status stays Live.
  - The Agent graph drawing does not change: there is still one `router` node.
- **e2e.** `web/e2e/exit-demo.spec.ts` matches `^Course note: Router · (brainstorm|query|edit)$`. The default stays LLM, so it still passes. Widen the pattern to allow the Jev suffix.

## Testing

- **Unit, API:**
  - the setting round-trip and its validation (`"jev"`, `"llm"`, a bad value gives 422, null gives 422, non-admin gives 403);
  - the router node with a fake classifier: the mode is set, the stamp carries engine and confidence, and the record is written with `cost_usd: null`;
  - Jev failure falls back to the LLM, with the record carrying `fallback_for`;
  - both failing gives no mode and the turn still runs;
  - the Feature map card names the engine;
  - the base URL is derived correctly.
- **Unit, web:**
  - the chip label for both engines;
  - `parseRouterMode` with engine and confidence;
  - TurnCost and Under the hood "not priced";
  - the Studio switch calls `putSettings` and is disabled when read-only.
- **Eval:** `test_router_eval.py` parametrised over both engines, each at least 13/15. Record the run in the evaluation doc.
- **Manual / e2e:**
  1. Switch to Jev in Studio and send the walkthrough 12 message; the chip shows `Jev nn%`.
  2. Open Under the hood and see the Jev record.
  3. Simulate a Jev failure (for example a bad `ROUTER_DECISION_MODEL`) and see the fallback note.

## Left to the builder

- The recording mechanism (custom callback event, or a direct handler call), as long as records and SSE events match the shapes above.
- Exact wording of the Studio control and the "not priced" labels, kept consistent with existing Studio copy.
- File and function names for the Jev classification, following the existing modules.

## Calls made by the designer (not asked of the author)

- Jev failure falls back to the LLM router for that turn, reusing the fallback note.
- No confidence threshold.
- The message is sent to Jev unwrapped.
- The switch lives in the Agent graph panel.
- The LLM chip label is unchanged, so only Jev decisions gain a suffix.
- The Jev model id is an env setting (`ROUTER_DECISION_MODEL`), not a Studio control.
- **Fail fast.** The Jev call has an explicit 10-second timeout and no retry; the LLM fallback is its retry. It uses the package's async `ainvoke`, which the package provides.
- **Cost line on a fallback turn.** Both router calls are recorded as `router`. The Router step shows the LLM call's dollar figure. "Not priced" appears only when a Jev call that is not priced actually returned tokens.
- **Double fallback.** If the LLM router itself then falls back to its named fallback model, that inner fallback's note wins, and the Jev failure stays visible as its own errored record in Under the hood.
- **Under the hood.** The Jev request is stored as `request.messages`, one user message holding the message text, plus the question and its criteria, so the existing renderer shows it. A small "Decision model" label beside the role is the only new display.
- **e2e.** Widen both the regex and the `.replace(...)` that strips the chip label in `web/e2e/exit-demo.spec.ts`.
