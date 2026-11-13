# When a model is missing or unsupported

What Sagaloom does when a model call fails: the model was removed from OpenRouter, its provider stopped serving it, the API key may not use it, the account is out of credit, and the other kinds of failure. As of 2026-11-13.

## In short

- **Sagaloom never switches to another model on its own.** Each role uses exactly one model, pinned to one provider, with OpenRouter's fallbacks turned off. A failed call fails visibly.
- **Every step fails safely.** Nothing is written to canon by a failed step, a failed contradiction check is never reported as "no conflicts", and a message the input guard could not check is not acted on.
- **The message says what happened.** It names the step, the model, the cause and what to do, and says "try again" only when a retry can help.
- **The cause is kept.** Under the hood and Studio → Guardrails show the failed call with OpenRouter's own words. A failed call costs nothing.
- **Recovery is manual.** An admin picks another model (Studio → Models and providers, or `GUARD_MODEL` in `api/.env` for the guard and router).

## How models are chosen

| Role | What it does | Where its model is set |
| --- | --- | --- |
| Chat agent | Answers, calls tools, drafts proposals | Studio → Models and providers (admin), default `CHAT_MODEL` |
| Contradiction judge | Checks each proposal against related canon | Studio → Models and providers (admin), default `JUDGE_MODEL` |
| Fact extractor | Reads pasted text, files and wiki pages on import | Studio → Models and providers (admin), default `EXTRACTOR_MODEL` |
| Input guard | Screens each message for injection and real-world harm | `GUARD_MODEL` in `api/.env` (not in the Studio dropdown) |
| Router | Picks query, edit or brainstorm mode | Uses the input guard's model |
| Embeddings | Turns entries into vectors for search | `EMBED_MODEL` (default `openai/text-embedding-3-small`) |

The choices are limited to the allowlist in [`api/sagaloom/allowed_models.json`](../api/sagaloom/allowed_models.json): the models the OpenRouter key may use. Each entry names the provider the model is pinned to. Every call is sent with `"provider": {"order": [<that provider>], "allow_fallbacks": false}` ([`api/sagaloom/llm.py`](../api/sagaloom/llm.py)), so OpenRouter never routes it to a different provider or model.

## Before any call: the allowlist checks

| Situation | What happens |
| --- | --- |
| A default model in the env (`CHAT_MODEL`, `JUDGE_MODEL`, `EXTRACTOR_MODEL`, `GUARD_MODEL`) is not on the allowlist | The API refuses to start, with `model not in sagaloom/allowed_models.json: <VAR>=<model>. Pick a listed model id.` (`validate_role_models`) |
| A model chosen in Studio is later removed from the allowlist | That role quietly goes back to its env default on the next call (`ModelSettings.get_model_settings`) |
| Someone tries to set a model that is not on the allowlist | The API answers 422 `model is not on the allowlist: <model>`; the Studio dropdown only offers allowlisted models |
| The allowlist file is edited | The change is read only at startup: restart the API |

These checks cannot catch a model that is on the allowlist but no longer served. That case surfaces at call time, below.

## At call time: the kinds of failure

[`api/sagaloom/model_errors.py`](../api/sagaloom/model_errors.py) sorts an OpenRouter error into one kind:

| Kind | How it is recognised | Typical cause | Retry helps? |
| --- | --- | --- | --- |
| `gone` | HTTP 404, or a 400 whose text says "not a valid model", "no endpoints", "model not found", "does not exist", "is not available", "no allowed providers" or "deprecated" | The model was removed from OpenRouter, or its pinned provider stopped serving it | No |
| `blocked` | HTTP 403 | The API key may not use this model (for example a guardrail allowlist on the key) | No |
| `no_credit` | HTTP 402 | The OpenRouter account is out of credit | Only after adding credit |
| `bad_key` | HTTP 401 | The API key is wrong, revoked or missing | No |
| `rate_limited` | HTTP 429 | Too many requests | Yes, after a moment |
| `rejected` | Any other 4xx | A request the model refuses (for example a parameter it does not support) | No |
| `timeout` | No answer within 60 s | A slow or stuck provider | Yes |
| `network` | No connection to OpenRouter | The internet or OpenRouter is down | Yes |
| `down` | 5xx, or an error OpenRouter returns inside a 200 answer | The provider had an error | Yes |

**Automatic retries before the message.** The OpenAI client retries connection errors, timeouts, 408, 429 and 5xx up to 3 times. The guard and router also try once more after such an error. `gone`, `blocked`, `no_credit`, `bad_key` and `rejected` are not retried: another try gets the same answer.

## What each step does, and the exact message

The `<model>` part is the model's id, e.g. `openai/gpt-6-luna`.

| Step | What happens | Example message (model removed) |
| --- | --- | --- |
| Chat agent | The turn stops with no reply | "The chat model (`<model>`) is no longer available on OpenRouter from its provider, so I couldn't reply. An admin can choose another model in Studio → Models and providers." (red, in Chat) |
| Input guard | The message is blocked and not acted on (fail closed) | "The input guard's model (`<model>`) is no longer available on OpenRouter from its provider, so I couldn't check your message and didn't act on it. An admin can set GUARD_MODEL in api/.env, or switch the input guard off in Studio → Guardrails." (as the guard's notice) |
| Router | The turn carries on without a mode | Nothing in Chat; the failed call is in Under the hood |
| Contradiction judge | The proposal still reaches the approval card, marked as not checked | "The contradiction judge's model (`<model>`) is no longer available on OpenRouter from its provider, so the contradiction check could not run and clashes with other entries are unknown. An admin can choose another model in Studio → Models and providers." (the card's check line; you can still Approve, Edit or Reject) |
| Fact extractor (Import page) | Nothing is imported, and the import thread is removed | "The fact extractor's model (`<model>`) is no longer available on OpenRouter from its provider, so nothing was imported. An admin can choose another model in Studio → Models and providers." |
| Fact extractor (agent's `import_wiki` tool) | Nothing is imported; the agent reports the same message | As above |
| Embeddings, while searching | `search_canon` returns `search failed: …` to the agent, which tells the author it could not search | The agent's own wording; not yet described by `model_errors` |
| Embeddings, while saving | The approved change is not saved; the review result says the commit failed | The commit failure message; not yet described by `model_errors` |

The same wording pattern holds for the other kinds, with the cause swapped in:

| Kind | Message pattern |
| --- | --- |
| `blocked` | "OpenRouter refused the `<role>`'s model (`<model>`): this API key is not allowed to use it, so … An admin can choose an allowed model in …" |
| `no_credit` | "The OpenRouter account is out of credit, so … Add credit at openrouter.ai, then try again." |
| `bad_key` | "OpenRouter did not accept the API key, so … An admin can check OPENROUTER_API_KEY in api/.env." |
| `rate_limited` | "OpenRouter is limiting requests to the `<role>`'s model right now, so … Wait a moment, then try again." |
| `rejected` | "OpenRouter rejected the request to the `<role>`'s model (`<model>`) (`<status>`), so … An admin can choose another model in …" |
| `timeout` | "The `<role>`'s model (`<model>`) took too long to answer, so … Try again in a moment." |
| `network` | "Sagaloom could not reach OpenRouter, so … Check the internet connection, then try again." |
| `down` | "The `<role>`'s model (`<model>`)'s provider had an error, so … Try again in a moment." |

An error that is not a model API error (a bug, a store failure) keeps the plain wording: "Something went wrong…", "The extraction could not run, so nothing was imported. Try again.", "I couldn't check that message just now…".

Imports are judged as a whole: when only some parts or pages fail, the rest is imported and each failed part is listed as "this part of the text could not be read". The named message appears only when every part failed.

## Where the cause is kept

- **Under the hood** (under any turn): the failed call's Response tab shows `Call failed: <kind> <status>: <OpenRouter's words>`, e.g. `Call failed: gone 404: No endpoints found for openai/gpt-x.`
- **Studio → Guardrails → Recent verdicts**: a failed guard call shows **error** with the same cause.
- **The prompt log** (`api/data/prompts.sqlite`): the record's `response.error` holds that line; its tokens and cost are 0, so a failed call never counts against the monthly budget.
- **The API log**: one warning per failure, with the kind and status.

## How to recover

| Cause | What to do |
| --- | --- |
| `gone`, `blocked` or `rejected` for the chat agent, judge or extractor | Studio → Models and providers: pick another model (admin only). The choice applies from the next call |
| The same for the guard or router | Set `GUARD_MODEL` in `api/.env` to an allowlisted model and restart the API. As a stopgap, switch the guard off in Studio → Guardrails: messages then go through unchecked. The router still uses the guard's model, but its failure only drops the mode, so chat works again |
| `no_credit` | Add credit at openrouter.ai |
| `bad_key` | Fix `OPENROUTER_API_KEY` in `api/.env` and restart the API |
| `rate_limited`, `timeout`, `network`, `down` | Wait and try again |
| A model has gone for good | Remove it from `api/sagaloom/allowed_models.json` (and from `api/sagaloom/model_ratings.json` if rated) and restart the API; a role that used it goes back to its env default |

## Not handled (known limits)

- **No automatic fallback.** A removed model breaks its role until an admin acts. A fallback list per role was discussed and not built.
- **No early warning.** Nothing checks the allowlist against OpenRouter's model list; a removed model is found on its first failed call.
- **Embeddings failures** are not described by `model_errors` yet (see the table above).
- **The retry decision is by status code.** OpenRouter's wording for a removed model can change; an unrecognised 400 is reported as `rejected`, which still says to choose another model.

## How it is tested

- [`api/tests/test_model_errors.py`](../api/tests/test_model_errors.py): each kind, its message, its retry flag, the model taken from the request or the call site, and the guard and router pointing to `api/.env`.
- [`api/tests/web/test_model_failures.py`](../api/tests/web/test_model_failures.py): the message at each place (Chat, guard notice, approval card, import), the cause in the prompt log and in Studio → Guardrails. All with fake OpenRouter errors: no real call, no cost.
- [`web/tests/UnderTheHood.test.tsx`](../web/tests/UnderTheHood.test.tsx) and [`web/tests/turns.test.ts`](../web/tests/turns.test.ts): "Call failed" in Under the hood.

**By hand:** add a fake model to the allowlist, restart the API, and select it for a role:

```json
{"id": "openai/gpt-does-not-exist", "price_in": 0.1, "price_out": 0.5, "provider": "openai"}
```

OpenRouter answers it with a `gone` error. Remove the entry and restart when done; it must not be committed.
