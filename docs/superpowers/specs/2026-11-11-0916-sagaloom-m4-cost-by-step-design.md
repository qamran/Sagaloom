# Sagaloom M4 design: cost by step

_Written 2026-11-11 after M3 closed (`f60675c`). `docs/requirements.md` remains the source of truth for requirements. This document says what M4 builds and records the decisions already made. Earlier designs: M1 `2026-11-04-sagaloom-design.md`, M2 `2026-11-05-0947-sagaloom-m2-design.md` and M3 `2026-11-09-2041-sagaloom-m3-design.md`. Mockups: https://claude.ai/artifact/47zGPGb6cvJGYwDJiMRRqQ (options 1 and 2 were chosen)._

---

## 1. Intent

Sagaloom already shows three things:
- the tokens and cost of a turn, in the Under the hood header (R14.1);
- a running total for the thread, in the header cost pill (R14.2);
- each model call's own tokens and cost, inside the drawer (R20.3).

What it can't answer is **"where did this turn's money go?"**. A turn runs several steps: the guard screens the input, the router picks a mode, the agent chats and calls tools, the judge checks a proposal against canon, and on imports the extractor pulls candidates. The Check step is usually the most expensive, because the judge reads the retrieved canon, and today the author can't see that.

M4 delivers R14.3 ("Break the cost down by step", currently a Could and a gap: no competitor has it). It does this in two places, both chosen by the user from the mockups:

1. **Under each turn (option 1, LitMemo's "cost per action").** A cost line goes under the last message of each turn, and it expands into a split by step.
2. **The drawer run tree (option 2, LangSmith's trace).** Under the hood groups its model calls by step, and each step gets a subtotal.

There is also a small rename. **Studio → Usage → "Cost by model"** becomes **"Cost by step"**, and its rows are labelled by step.

## 2. Goals, non-goals, anti-goals

**Goals**
- After every turn, chat shows that turn's tokens and cost under the turn's last message, and the line expands into a per-step split. The split has a stacked bar plus one row per step, giving calls, tokens in → out and US$.
- The line is still there after a page refresh and after an API restart, because it comes from the prompt log (Ruling R16: the PromptLog is the source of truth for usage).
- In Under the hood, the "Prompts sent to OpenRouter" section groups calls under step headers. Each header shows the step's calls, tokens, cost and share of the turn, and contains that step's call cards as they look today.
- Studio's Usage panel reads "Cost by step", and each row is labelled by its step, for example "Check (Luna)".
- In every view the step figures add up exactly to the turn's figures (or, in Studio, to the overall figures).

**Non-goals**
- A per-step breakdown of the whole session in the header pill (option 3). The pill stays as it is, with no link and no popover.
- Per-step cost on the Import page's progress view. An import's Under the hood still gets option 2, because the drawer component is shared.
- Cost per tool. Two tools do call models: `create_or_update_entry` and `check_contradiction` call the extractor through `draft_facts`, and `check_contradiction` also calls the judge (`api/sagaloom/tools/canon_tools.py`). Those calls count under their role's step (Extraction and Check), not under the tool.
- Embedding cost. Embeddings aren't chat-model calls and aren't in the prompt log today. Leave that as it is.
- Budgets, alerts or cost limits.
- Course-review preparation. The user will say when (handoff §3 rule 9).

**Anti-goals (a failure even if it works)**
- Step figures that don't add up to the turn total, or a turn total that differs from what R14.1 shows today.
- Linking a turn to its messages by position or by matching text. Like Ruling R-W5-7 ("structured, not text-matched"), the link must be a stored turn id.
- A change to the SSE event set (`token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`).
- Sending the full prompt log to the chat page just to draw cost lines. The log holds whole prompts, so the cost lines need a small summary instead.
- Weakening an existing invariant: verbatim records, secrets masking, no API key in any record, or the guard failing closed.

## 3. Decisions

### 3.1 What a step is (decided; the mapping is Claude's call)

A step is the `role` already stored on every prompt record. The app tags the role on each model (`api/sagaloom/web/app.py` `model_for`). Display names, in this fixed order:

| Order | `role` | Step name | What it is |
|---|---|---|---|
| 1 | `guard` | Guard | Input screen (R13.1) |
| 2 | `router` | Router | Mode pick (brainstorm, query or edit) |
| 3 | `agent` | Chat | The agent's replies and tool-calling turns |
| 4 | `judge` | Check | Contradiction check against canon, from the `check` node or the `check_contradiction` tool |
| 5 | `extractor` | Extraction | Pulling facts out of text: import candidates, and the fact drafts that `create_or_update_entry` and `check_contradiction` make during chat turns |
| 6 | anything else or null | Other | Older records or untagged calls |

Rows always appear in this order, not in the order calls happened, and a step with no calls isn't shown. So an ordinary edit turn in chat will usually show an Extraction row as well (Claude's call to keep the name "Extraction" for it: it is the same model doing the same job). **The mapping lives in one place in the web app** (a small `lib/steps.ts`, or an extension of `usageLabel` in `UsagePanel.tsx`). The server groups by raw `role` and never needs step names. Today `usageLabel` maps judge to "Judge". After M4 the same map gives "Check", so Studio and chat use one vocabulary.

### 3.2 Option 1: cost line under each turn (decided by the user; details are Claude's call)

- **Where:** directly under the last message of the turn that chat **displays**. Today that means the user, assistant, review, guard and memory roles (`ChatThread.tsx`: `tool` and `import` messages render nothing). On a turn paused at the approval gate, the line sits after that turn's messages and **above** the approval card. If a turn has no model calls (for example a pure decision with no follow-up reply), or has no displayed message, it gets no line. An import's own turn is one example: its cost shows in the drawer, not in chat.
- **Collapsed:** `1,234 tokens · $0.0063 · 4 steps ▸`, small and muted, with the same look as the existing meta text. It is a button with `aria-expanded`.
- **Expanded:** a compact panel holding a stacked bar (one segment per step, sized by cost) and one row per step: the step name with its colour key, the call count, `in → out` tokens, and US$ to 4 decimals. Then a Total row. Tokens use tabular numbers. For the step colours, use existing tokens from `globals.css`, Claude's call. The mockup used rule, place, accent, event and faction.
- **Expanded state** is per turn, kept in memory, and lost on refresh. Nothing is persisted.
- **While a turn is streaming,** there is no line yet. The line appears once the turn ends (§3.4 says how the messages and figures reload).
- **Old messages** have no turn id because they were written before M4, so they get no line. The drawer still shows those turns as it does today, and that's acceptable.

### 3.3 Turn ids on messages (constraint decided; mechanism is the builder's)

The cost line needs to know which messages a turn wrote. **Every message of a displayed role (user, assistant, review, guard, memory) that a turn appends carries that turn's id.** That id is the same `turn_id` the PromptLog handler stamps as each record's `run_id`. It's stored the way `mode` already is on user messages (`additional_kwargs`) and returned by `GET /api/threads/{id}` as `turn_id` on each message.

Tool and import messages don't need the id, so `tools_node` doesn't need wrapping (Claude's call). The author's own message does carry it. That message is built in the route (`routes.py` around line 461) before `_turn` creates the id (line 175), so the id has to be created earlier and passed in. A turn that spends money and then fails with no reply still gets its line, under the author's message.

The builder works out how the id reaches the nodes that append messages, presumably through the graph config's `configurable`. This covers chat turns and decision (resume) turns. Messages written before M4 lack the field, and everything must handle that.

### 3.4 Per-turn usage summary from the API (decided)

`GET /api/threads/{id}` gains a `turns` list. It is ordered by the turn's first record, and each item looks like this:

```json
{ "turn_id": "…", "usage": { "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0 },
  "by_role": [ { "role": "judge", "calls": 1, "prompt_tokens": 3420, "completion_tokens": 210, "cost_usd": 0.0028 } ] }
```

- It is computed from the PromptLog: group by `run_id`, then by `role`. Add a PromptLog method next to `usage()` and `usage_by_model()`. Its totals must equal `promptlog.usage(thread_id, run_id)`.
- No new endpoint and no SSE change. **How the chat gets the data (Claude's call, after the builder check):**
  - The chat page has no thread query. Its messages are local state in `useAgentStream`, which reads the server's messages only on load and after decision turns (`await restore()`, `useAgentStream.ts` around line 305). Messages streamed during a chat turn never get a `turn_id`.
  - So **`useAgentStream` re-reads the thread (`restore()`) after every turn that ends with `done`**, not only after decision turns. It also exposes `turns` from that same response.
  - The streamed messages are swapped for the server's copies. Visible jumps from that swap (for example in how tool activity lines render) count as bugs to fix in the task.
  - `ReviewDetail.tsx` shares the hook and counts review notes. The task must keep its tests green and check that its counts don't change.
  - The header pill's `["thread", id]` query keeps its own invalidation, as today.
- `GET /api/threads/{id}/llm-log` (the full prompts) stays drawer-only and still loads lazily.

### 3.5 Option 2: drawer grouped by step (decided by the user; details are Claude's call)

- **Where:** inside `UnderTheHood.tsx`. The "Prompts sent to OpenRouter" list becomes step groups in the §3.1 order.
- **Group header:** the step name with its colour key, `N calls · in → out tok`, the step's US$ and a thin bar showing its share of the turn's cost. Each header is a disclosure. **The group that costs the most starts open,** and the others start closed. Today only the first call is open by default; now that call opens only if it's in the most expensive group.
- **Inside a group:** the existing `CallCard`s, unchanged, in call order. **Each card keeps its index in the whole turn** (e.g. "#3"), so the order of calls is still readable after grouping. The cards keep their descriptive labels from `ROLE_LABEL` (`UnderTheHood.tsx` around line 51), such as "Contradiction judge" and "Fact extractor" (Claude's call). The group header gives the step name, and the card says which model job it was. This is the one place where the step name isn't used on its own.
- **The drawer header** (`Turn n · k model calls · $x · y s`), the graph path, the tool calls, secrets masking and "Copy turn as JSON" stay as they are. Copy still copies the calls in call order, not grouped.
- **The data is the client-side `TurnView.calls` it already has**, live or from the log. No new fetch.

### 3.6 Studio rename (decided)

- In `UsagePanel.tsx`, the heading "Cost by model" becomes **"Cost by step"**.
- Row labels use the §3.1 step name plus the short model name: "Check (Luna)", "Chat (Luna)", "Extraction (Luna)". Unknown roles stay as the bare model id, as they are today.
- The aggregation (`usage_by_model`, one row per role and model) and the row order (highest cost first) stay the same. The section `id="usage"` and the empty-state copy stay the same.
- Update the tests that assert "Judge (…)" or "Cost by model" (`web/tests/FeatureMap.test.tsx` around lines 109–124).

### 3.7 Requirements and docs

- `docs/requirements.md` R14.3: change the priority from Could to **Should (M4)**, and fill in "Done when". Every turn with model calls shows a per-step split under its last message that adds up to the turn total and survives a refresh, and Under the hood groups the calls by step with subtotals. Then add a change-log row.
- In the competitor table, R14.3 stays listed under "Gaps".
- README: add one line to the features list.
- At the end, update `internal docs/handoff.md`: M4 done, backlog minus cost by step.

## 4. Constraints

- **Stack and patterns as M1–M3.** FastAPI and LangGraph in `api/`, Next.js 16, React Query and Tailwind tokens in `web/`. No new dependencies.
- **Tests:**
  - API: a unit test for the PromptLog per-turn and per-role aggregation, including a turn with mixed roles and a record with a null role;
  - API: a route test that `GET /threads/{id}` returns `turns` and `turn_id` on the messages of a scripted turn (chat, then a decision);
  - web: a unit test for the role → step map and ordering;
  - web: component tests for the turn cost line (collapsed, expanded, sums, no line without a turn id) and for the drawer grouping (order, subtotals, the most expensive group open, card indexes kept);
  - web: an update to the UsagePanel test.
  - Whether to add an e2e step is the builder's call.
- **Process (handoff §3):** a milestone "M4: cost by step" in both repos, with issues per task (starting at #98) and `Refs`/`Closes` trailers. Build with subagent-driven development (Sonnet or Opus builders), give each task an Opus review and finish with a Fable review. Review findings and their resolutions go in each issue, in both repos. Push to `main` on both remotes, but only after the user confirms.
- **Size:** one wave, expected 4 to 6 tasks: API turn ids, API summary, web step map and Studio rename, turn cost line, drawer grouping, docs.

## 5. Left to the builder

- How `turn_id` reaches the nodes that append messages, and which nodes those are.
- Exact Tailwind classes and colour token choices for the steps, within the existing tokens.
- Where the shared step map lives, and whether `usageLabel` absorbs it.
- How `restore()` after every turn avoids flicker, for example by keeping scroll position.
- What counts toward a step's calls: a failed call counts as a call but adds 0 tokens, as `promptlog.usage()` already does.
- Whether an e2e step is worth adding.
