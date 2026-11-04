# Sagaloom: design

**Date:** 2026-11-04
**Status:** draft, awaiting the student's approval
**Companion documents:**
- `docs/requirements.md`: the detailed requirements. Its IDs are cited below, and it is the source of truth for behaviour and "Done when" tests.
- `135.md`: the course brief.
- UI mockups (canvas): https://claude.ai/artifact/UesPwxSN3tj2RkuHG2pKK2
- Stack decision: `internal docs/tech_stack_decision.md` (not committed; summarised in section 5)

---

## 1. Intent and why

Writers and game masters who build a fictional world over months suffer **canon drift**: a city's founding date, the number of moons or who rules what quietly changes from one note to the next. Chatbots make this worse, because they invent lore with confidence. Existing tools either generate content (LoreKeeper), check continuity only on demand or only on paid tiers (Realmweaver, StoryGuard), or work only in Chinese and on manuscripts (LitMemo).

**Sagaloom is a continuity editor, not a ghostwriter.** It keeps the world's canon as entries made of prose plus short **facts**. Nothing enters canon without the author's approval, and **every proposed change is checked automatically**, fact against fact and then prose against prose. Conflicts are shown with the clashing values side by side, the IDs of the entries involved, and a suggested fix. The author can also keep an idea as a **myth or rumour**, which never counts as a hard conflict.

It is also a Turing College Sprint 3 project. It must satisfy the brief (LangGraph/LangChain, the OpenAI API, memory, a UI, error handling and documentation) and secure at least 2 medium and 1 hard bonus task. The M1 build alone guarantees 2 medium and 2 hard (R14, R10.1, R7/R11.1, R15.1).

**Target users:** fantasy and sci-fi authors, fan-fiction writers, and solo tabletop game masters (R1.2).

---

## 2. Goals, non-goals, anti-goals

**Goals**
- Catch contradictions **before** they enter canon, on every write, with cited entry IDs and facts (R4.2, R4.3, R11.3).
- Make the author the final judge: approve, edit then approve, save as myth, or reject (R5, R18).
- Answer questions from the author's own canon and say "not in canon" rather than invent (R7).
- Import existing lore (pasted or uploaded notes, fan-wiki pages) as reviewable batches (R3, R11.6).
- Look and feel like a real product, comparable to the competitors' web apps.

**Non-goals (this project)**
- Writing manuscripts, serial publishing, manga or image generation (LitMemo's territory).
- Running game sessions: recaps, initiative, player accounts (StoryGuard's territory).
- Maps and a visual relationship canvas (R12.7, Won't).
- User accounts and multi-user collaboration (out of scope; a shared API secret protects the deployment).
- A Ragas or DeepEval report (R15.2, Won't, by the student's choice).

**Anti-goals: it fails even if it technically works when**
- It writes lore *for* the author unasked, or changes canon without approval.
- It reports "no conflict" when the check didn't actually run (fail closed, R11.3.7).
- It blocks dark fiction (war, cults, murder) as "unsafe" (R13.1).
- Imported text can steer the agent (R13.6–R13.8).
- It needs a live third-party service to give the review demo (R11.6.11; local run is the primary demo).

---

## 3. Constraints

- **Brief:** "Streamlit or Next.js"; LangGraph/LangChain; OpenAI API; memory. Next.js is the named option chosen.
- **LLM access:** OpenRouter's OpenAI-compatible API, with the key in `api/.env` (R11.G5). Whether this counts as "the OpenAI API" is an **open question for the reviewer**. The design keeps a switch to call OpenAI directly.
- **Model and provider are pinned** for reproducible tests (R11.G7).
- **No fixed time budget.** Scope is controlled by milestones M1 (core demo), M2 and M3 (requirements, "Milestones").
- **Fandom terms of use:** accepted risk K1, to revisit before any commercial use. Honest User-Agent, no getting around blocks (R11.6.9).
- **Licences:** imported wiki text carries its real licence from the wiki's API, with non-commercial warnings and a share-alike notice in exports (R11.6.12, R11.6.13, R11.5.5).

---

## 4. What the student decided

### 4.1 Product shape: one product, four tabs, Canon is home

Decided on the canvas. The three earlier layout options became tabs of one product (R12.9):

| Tab (route) | Job | Based on | Milestone |
|---|---|---|---|
| **Canon** `/canon` (home) | Browse the world bible. Entry page with section cards, a **Facts** panel, "Mentioned in" chips, and a floating assistant | Realmweaver entry page; LitMemo floating assistant and filters | Basic page in M1 (list, body, facts, read-only); full page in M2 |
| **Chat** `/chat/[threadId]` | Ask, add and brainstorm. A single change is approved **inline** in a "Commit to canon?" card with a fact table | StoryGuard and LitMemo confirm cards | M1 |
| **Review** `/review` | Queue for batches (imports), detail view with a 4-column fact comparison, bulk actions | Realmweaver import review | M2 |
| **Import** `/import` | One page with three source cards: Paste text, Upload `.md`/`.txt`, Fan wiki. "Recent imports" list. Everything lands in Review | Our own mix | M2 |

### 4.2 Interface patterns (from the competitor screens)

- **Colour-coded entity chips** by type, used everywhere an entry is named, with `@` linking in the composer (R12.10; StoryGuard, LitMemo).
- **Facts alongside prose** on every entry, which the checker compares first (R2.11, R11.2.9, R11.3.3; Realmweaver).
- **Secrets hidden** until you click Show, safe for screen sharing (R12.12; StoryGuard).
- Ctrl+K search, a card grid and a floating assistant (R12.13, Could; LitMemo).

### 4.2b Showcase for the course review (R20)

The project is graded, so the UI shows its features rather than hiding them.
- **Studio page (`/studio`)**, a "Developer" tab set apart in the header. It holds the Feature map (one card per brief requirement and bonus task, each with Live / Configured / Off status and a "Try it" link), the agent graph, tools, models and providers (OpenRouter, plus Gemini "demo only"), memory, guardrails, usage and developer settings. It is **a separate page, not a settings modal** (my call): diagrams and logs need room, and the brief asks for developer settings to be kept apart from the user experience.
- **Under the hood drawer in Chat:** per turn, it shows the graph nodes passed, the tool calls, and **every prompt sent to OpenRouter exactly as sent**, plus the response, tokens and cost. A LangChain callback captures the requests (never the API key), streams them as `llm_request` and `llm_response` events, and stores them per thread.
- **Course annotation chips** at the moments a feature acts, linking to the Feature map, with an on/off toggle.

### 4.3 First run

The app opens on the Canon home with the **Velmar** demo world loaded and a dismissable **"Get started" checklist** (LitMemo-style):
1. Browse an entry (Sky of Velmar).
2. Ask a question in Chat.
3. Add a fact that breaks canon ("Velmar has three moons").
4. Resolve it by saving it as a myth.

Steps tick themselves off. Velmar is loaded automatically on first run. "Start my own world" creates a new, empty world **alongside** Velmar, and a world picker in the header switches between them. Every entry, search and thread is scoped by world (R10.4, R10.5).

### 4.4 Conflict handling

A conflict offers **Save as myth** as the primary action, plus Edit, Approve anyway and Reject. **Save as myth** keeps the existing canon and adds the clashing claim as a *myth fact* on the same entry, e.g. Sky of Velmar keeps "Moons: One" (canon) and gains "Moons: Three" (myth, told by the Ashen Choir). Facts and entries marked myth or rumour produce notes, never hard conflicts. Secrets are true, so they are checked like canon and only hidden on screen. Definitions: the Glossary in `docs/requirements.md` (R2.8, R4.6, R5.6, R11.3.5).

**Retcons:** changing one of an entry's *own* canon facts (Sky of Velmar "Moons: One → Three") is never silent. It gets a **Retcon** badge, softer than a conflict, and needs confirmation. Clashes with *other* entries (e.g. Ister) are still shown as conflicts on the same card. Retcon detection is deterministic code, comparing the old and new facts (R11.3.10).

### 4.5 Stack

Decided after the Fable judge's review (8.5/10; runner-up React + Vite at 7.6):

| Layer | Choice |
|---|---|
| Front end | **Next.js 16** (React 19, TypeScript), App Router |
| UI kit | **shadcn/ui + Tailwind v4**; TanStack Query for server state; a small hand-written SSE hook (`useAgentStream`) |
| Agent back end | **Python, FastAPI, LangGraph** |
| API | Hand-written JSON + **SSE** contract (R19), **not** LangGraph Agent Server, because of the cost of the licence or hosting plan |
| Vector store | **Chroma**, embedded `PersistentClient` under `data/chroma` (R10.3) |
| Checkpointer | **`AsyncSqliteSaver`** under `data/` (R18.7); LangGraph Store for author preferences (R10.2) |
| LLM and embeddings | OpenRouter (OpenAI-compatible). **Every role defaults to `openai/gpt-6-luna`** (agent, contradiction judge, fact extractor, guard); embeddings `openai/text-embedding-3-small` (R11.G6). Each role can be switched in the Studio page to another allowlisted model, e.g. Terra or Sol for the judge (R11.G10) |
| Second provider (demo only) | Google Gemini direct through its OpenAI-compatible endpoint, optional `GEMINI_API_KEY`, `gemini-3.5-flash-lite` only. It shows multi-provider support and is never used for tests or evals (R11.G8, R11.G9) |
| Security | Next.js route-handler **proxy** that injects a server-side shared secret; CORS allowlist; body cap; rate limit (R13.3, R13.4) |
| Observability | LangSmith via environment variables, one thread per `thread_id` (R15.1) |
| Testing | pytest (API, tools, graph), Vitest (components), **Playwright** (the M1 exit demo, including refresh) (R15.3) |
| Packages | **uv** (Python), **pnpm** (web) |
| Hosting | Local run is the primary demo. Optional deployment on Vercel (web) + Railway with a volume (API) |

**Repo layout:** `api/` (FastAPI and the agent), `web/` (Next.js), `seed/` (Velmar demo world), `docs/`. `data/` is git-ignored.

### 4.6 Agent architecture

As specified in R18:

```
guard → router → agent ⇄ tools
                    tools → check → approval_gate (interrupt) → commit
```

- The **graph** enforces that every proposal from `create_or_update_entry` or `import_wiki` passes through `check` and `approval_gate`. The LLM can't skip it (R18.2).
- `commit` refuses any proposal without a check result and an approve decision (R18.3). Edits are checked again (R18.4).
- Deletes get a dependency check instead of a contradiction check (R11.2.8).
- Paste and upload imports start their own thread. Extraction runs with no tools bound, and the graph enters at `check`, so imports also pass `check` and `approval_gate` (R18.10). Review lists every thread with a pending approval, from chat or import.
- Every entry, search, check and thread is scoped by `world_id` (R10.4).
- Six tools, each specified in R11.1–R11.6.

### 4.7 Visual identity

**My call, not yet confirmed by the student:**
- **Theme:** dark and literary.
- **Fonts:** Newsreader serif for headings, Inter for body text.
- **Colours:**
  - ink-green background
  - verdigris accent (`#6FBFA8`)
  - amber for conflicts (`#E8A15A`), so actions and conflicts differ in both hue and lightness
- **Entity colours:** character violet, place green, faction pink, rule blue, event gold.

The canvas shows it.

---

## 5. Data flow for one change (the core loop)

1. The user types in Chat. The web app sends `POST /api/threads/{id}/messages` through the proxy, and the API streams SSE events back.
2. `guard` classifies the input. `agent` calls `search_canon`, then `create_or_update_entry`, which adds a proposal with drafted facts to state.
3. `check` compares facts and then prose, and stores the result.
4. `approval_gate` calls `interrupt()`, and the stream emits an `interrupt` event. The Chat card renders it.
5. The user decides. `POST /api/threads/{id}/decisions` resumes the graph. Approve leads to `commit` (Chroma write, `version`+1). Edit leads back to `check`. Reject tells the agent.
6. `usage` events update the cost display. On refresh, `GET /api/threads/{id}` restores the pending card and the totals (R5.5, R14.2).

---

## 6. Left to the builder

- The **pinned provider** for `openai/gpt-6-luna` (R11.G7). The model is decided: GPT-6 Luna for every role, switchable in Studio (R11.G10).
- The **prompts**: the system prompt, the guard policy text (R13.1), and the fact-extraction and judge prompts (R11.3).
- **How facts are stored in Chroma**: as JSON metadata, or as separate small documents for the facts-first pass (R2.S storage note).
- The **seed world content** for Velmar: 15–20 consistent entries with facts, at least one myth and one rumour, and two scripted contradicting proposals (R2.10).
- Internal module structure inside `api/` and `web/`, within the R19 contract.
- Exact visual polish beyond the canvas: spacing, motion and empty states.
- Whether to deploy, and where. The local run is enough for the review.

---

## 7. Calls I made (please check)

These came up in the builder review and were settled without asking. Each can be changed.
1. **The demo's "planted contradictions"** are two scripted proposals that clash with a *consistent* seed world, such as "Velmar has three moons". The seed itself has no contradictions, so M1 needs no whole-world scan (R2.10, R4.9).
2. **Imports enter the graph at `check`** through their own thread, rather than going through the tool-calling agent. That keeps untrusted text away from an LLM with tools bound (R18.10, R13.6).
3. **Secret counts as canon for checking.** It's true, just hidden on screen. This corrects an earlier requirement that treated it like a myth.
4. **The visual identity** in 4.7.

---

## 8. Open questions

1. **OpenRouter vs "OpenAI API":** confirm with the reviewer that OpenAI models through OpenRouter are acceptable (R11.G5).
2. **The visual identity** in 4.7 is my call, and the student may still change it.
