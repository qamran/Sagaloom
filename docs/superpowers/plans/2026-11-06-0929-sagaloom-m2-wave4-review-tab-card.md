# Sagaloom M2 Wave 4 (Review Tab and the Upgraded Approval Card) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pending decision in the active world is visible in one place, and each card shows exactly what will change.
- A **Review tab** (`/review`, `/review/[threadId]`) lists the threads waiting on a decision and lets the author decide a whole batch with one submit.
- The **approval card** shows old against new: a complete 4-column fact table on updates, a title/type/status line diff, a word-level body diff, severity badges, and each flag's suggested fix under its own row.
- The server sends **one retcon flag per stored fact**, adds a **near-duplicate note**, gives **one card per entry** in a batch, handles a **renamed key in Save as myth**, and uses one "check failed" text.
- An eval shows consistent proposals rarely raise hard conflicts (R4.10).

**Architecture:**
- **Server.** The check pipeline stays deterministic around the judge: `detect_retcons` (per stored fact), a new `check/duplicate.py` (near match, no LLM), and a new `check/badge.py` that derives one badge per check result. The badge is added to the interrupt payload at the API edge (routes and SSE), so old checkpoints get it too. `merge_proposals` replaces a pending proposal for the same `entry_id` in place. `GET /threads` takes `world_id` and returns title, created time and worst badge.
- **Web.** A pure `lib/factRows.ts` turns a proposal and its check into table rows; `FactTable` renders them; a new `DiffView` renders the line and body diffs with `diff`'s `diffWords`. `useAgentStream` gets an `autoSubmit` option so the Review detail can collect decisions and send them with one "Submit N decisions" button. The header gets a polled Review tab with a count.
- **Graph:** unchanged. No new node or edge, so the Mermaid blocks don't change.

**Tech Stack:**
- API: Python 3.12, FastAPI, LangGraph 1.2.19, pytest.
- Web: Next.js 16, React 19, TanStack Query, `diff` **9.0.0** (new dependency, pinned exactly; it ships its own types), Vitest, Playwright.

**Spec:**
- `docs/superpowers/specs/2026-11-05-0947-sagaloom-m2-design.md`: §2 Wave 4, §3.6 (Review tab), §3.7 (old vs new), §3.8 (severity and fixes), §3.9 (duplicates).
- `docs/requirements.md`: R12.9, R18.5, R5.4, R4.4, R4.5, R4.10, R11.2.4, R19.1.
- Mockup: canvas artifact https://claude.ai/artifact/UesPwxSN3tj2RkuHG2pKK2, file `project/ReviewPanel.dc.html` (queue left, card right, 4-column table, "Approve 1 with no issues", "Reject all").
- Deferrals folded in:
  - M1 final review (`.superpowers/sdd/2026-11-04-sagaloom-m1-core-demo/final-review.md`): **M3** one retcon flag per stored fact; **M7** edit-form limits and field names in 422s; **M10** the two "check failed" strings, and `GET /threads` cost.
  - Wave 1 Fable review: renamed key in Save as myth.
  - Wave 2 Fable review: two e2e timing minors (a failed decision only fails after the 120 s wait; the 1→0→1 card poll gap).
  - Already done, not repeated: the declarative eval accepting `ent_0012` (`api/tests/eval/test_answer_eval.py:246`).

**Issues** (both repos, milestone "M2: bonus tasks and points of difference"):

| Task | Issue | Builder |
|---|---|---|
| Task 0 (this plan) | #40 | — |
| Task 1: server check and batch upgrades | #41 | Opus |
| Task 2: card upgrades | #42 | Opus |
| Task 3: Review tab | #43 | Sonnet |
| Task 4: false-alarm eval, demo, docs | #44 | Sonnet |

The Fable wave-review fixes get #45. Each commit carries `Refs: #N`; the task's last commit carries `Closes: #N`.

## Global Constraints

- Work goes straight onto `main`. Push to both remotes (`origin`, `sagaloom`) only after the user confirms.
- **Invariants:** tools never write; only `commit` writes canon, after a check and an approve decision; only `remember` writes preferences; statuses are per fact; secrets stay masked on screen; PromptLog is the usage source of truth; **the SSE event set is unchanged** (`token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`); decisions resume at the gate and never pass through the guard or router.
- **The graph does not change.** `tests/graph/test_diagram.py` must pass untouched.
- Any new class stored in graph state lives in `api/sagaloom/models.py` (the strict checkpoint serde allows only that module).
- **Fixes are guidance, never actions** (R4.5, spec §3.8): no "Apply fix" button. Card actions stay Save as myth / Edit / Approve (anyway) / Reject.
- **Badges** (spec §3.8, one source: `check/badge.py`), worst first:

  | `badge` | Card/queue label | Colour |
  |---|---|---|
  | `conflict` | Conflict | amber fill (`bg-conflict`) |
  | `failed` | Check failed | `bg-destructive` |
  | `possible` | Possible conflict | amber outline (`border-conflict text-conflict`) |
  | `retcon` | Retcon | gold (`bg-event`) |
  | `note` | Note | violet (`bg-myth`) |
  | `clear` | Clear (queue) / No conflicts found (card) | `bg-accent` |

- **Result column values** (spec §3.7): `Matches`, `Changed (retcon)`, `Conflict`, `Possible conflict`, `Note`, `New`, `Removed`, plus `Changed` for a changed myth or rumour value, which raises no flag (ruling in Task 2).
- **Form limits mirror the schema:** title 1–120, body ≤4000, fact key 1–40, fact value 1–200, told by ≤120.
- **Copy, exact:**
  - Check failed (one constant, server): `The contradiction check could not run, so clashes with other entries are unknown. Review this change carefully before approving it.`
  - Check failed (card alert, unchanged): `The contradiction check couldn't run. Review this change yourself before approving.`
  - Duplicate note explanation: `Possible duplicate of <id> '<title>'`
  - Review empty state: `Nothing to review. Every change the assistant proposes waits here until you decide.`
  - Review detail lead: `<n> proposals · nothing enters canon until you decide`
  - Bulk buttons: `Approve <n> with no issues`, `Reject all`; submit: `Submit <n> decisions` (`Submit 1 decision` for one).

## Review Focus

1. **Secrets in the complete table.** Rows that come from the entry's own facts (not from flags) must still mask a secret fact, every fact of a secret entry, and the body diff of a secret entry. Pinned in Task 2 (`masks own secret facts in the complete table`, `masks the body diff of a secret entry`).
2. **Mixed-status facts under one key.** Canon `Members: About sixty` and secret `Members: Ashen Choir` under one key must give two retcon flags, and only the secret one is masked. Pinned in Task 1 (`test_one_retcon_flag_per_stored_fact`) and Task 2 (`masks only the secret retcon row`).
3. **Two parallel `create_or_update_entry` calls for one entry** (one AI message) must give one card, not two, and the card shows the second call. Pinned in Task 1 (`test_same_entry_proposals_collapse_to_one_card`).
4. **A re-check after Save as myth or Edit opens a new interrupt on the same thread.** The Review detail must show the new cards rather than an empty "done" screen. Pinned in Task 3 (`shows the re-asked card after a myth decision`).
5. **A checkpoint written before this wave** (interrupt payload without `badge`) must still list and render, with the badge derived at read time. Pinned in Task 1 (`test_pending_payload_gets_badges_for_old_checkpoints`).

---

### Task 0: Plan and issues (#40)

- [ ] **Step 1:** Create issues #40–#44 in both repos, in order, with the standing body sections and the `status: to do` label.
- [ ] **Step 2:** Commit this plan as `docs: M2 Wave 4 plan`, with `Closes: #40`.

---

### Task 1: Server check and batch upgrades (#41)

**Builder: Opus** (retcon and secret handling).

**Files:**
- Create: `api/sagaloom/check/duplicate.py`, `api/sagaloom/check/badge.py`, `api/tests/check/test_duplicate.py`, `api/tests/check/test_badge.py`
- Modify:
  - `api/sagaloom/check/retcon.py`: one flag per stored fact
  - `api/sagaloom/check/myth.py`: renamed-key rule
  - `api/sagaloom/check/contradiction.py`: public `CHECK_FAILED_EXPLANATION`; duplicate flags on creates
  - `api/sagaloom/graph/nodes.py`: `_failed_result` uses `CHECK_FAILED_EXPLANATION`
  - `api/sagaloom/graph/state.py`: `merge_proposals` replaces by `entry_id`
  - `api/sagaloom/tools/canon_tools.py`: invalidate a stale check when an earlier step's proposal is replaced
  - `api/sagaloom/web/routes.py`: `GET /threads` params and fields; `_pending` adds badges
  - `api/sagaloom/web/sse.py`: the `interrupt` event adds badges
  - `docs/requirements.md`: decision log, R19.1 and R12.9 wording
- Test: `api/tests/check/test_retcon.py`, `test_myth.py`, `test_contradiction.py`, `api/tests/graph/test_graph.py`, `api/tests/graph/test_state.py` (or wherever `merge_proposals` is tested), `api/tests/web/test_routes.py` (or the existing thread-route test file), the SSE test file

**Interfaces:**
- Produces:
  - `CHECK_FAILED_EXPLANATION: str` in `check/contradiction.py` (copy in Global Constraints). `_FAILED_EXPLANATION` is removed.
  - `Badge = Literal["conflict", "failed", "possible", "retcon", "note", "clear"]` and `BADGE_ORDER: tuple[Badge, ...]` in that order, in `check/badge.py`.
  - `def badge_of(result: CheckResult) -> Badge`:
    - `failed` if `verdict == "failed"`;
    - else `conflict` if any `kind == "conflict"` flag has `severity == "hard"`;
    - else `possible` if any `kind == "conflict"` flag;
    - else `retcon` if any `kind == "retcon"` flag;
    - else `note` if any flag;
    - else `clear`.
  - `def worst_badge(badges: Iterable[Badge]) -> Badge | None`: the earliest in `BADGE_ORDER`; `None` when empty.
  - `def with_badges(value: dict) -> dict` in `check/badge.py`: returns a copy of an interrupt payload whose every `checks[id]` dict gains `"badge"` (validated through `CheckResult.model_validate`). Used by `routes._pending` and the SSE `interrupt` event; the gate's payload is unchanged.
  - `def duplicate_flags(store, world_id: str, draft: EntryDraft) -> list[Flag]` in `check/duplicate.py`. Rule (spec §3.9), for each entry in the world, **at most one flag per entry, at most 3 flags**:
    - title tokens: `re.findall(r"\w+", norm(text))`, minus `{"the", "a", "an", "of"}`;
    - overlap `|A ∩ B| / max(|A|, |B|) >= 0.6` between the draft title and the entry's title or any alias; **or**
    - the top hit of `store.search(world_id, draft.title, k=1)` scores `>= 0.92`.
    - Flag: `kind="note"`, `severity="note"`, `entry_id`/`title` of the match, `explanation="Possible duplicate of <id> '<title>'"`, `existing_secret = entry.status == "secret"`.
  - `check_proposal` appends `duplicate_flags(...)` for `action == "create"` on **every** path (no related entries, judge result, failed). A duplicate note never changes `verdict`.
  - `detect_retcons(before, after) -> list[Flag]`, per key whose established value set changed:
    - `dropped` = stored established facts whose `norm(value)` is not among the new values; `added` = new values not among the old ones.
    - One flag **per dropped fact**: `fact_key=f.key`, `existing_fact=f.value`, `new_fact=", ".join(added) or None`, `existing_secret = before.status == "secret" or f.status == "secret"`, explanation `Changes established canon: <old> → <added>` or `Removes established canon: <old>`.
    - When nothing was dropped (pure addition): one flag for the key, citing the first stored fact, `existing_fact` = that value, `new_fact=", ".join(added)`, explanation `Adds to established canon: <added>`, `existing_secret` true if any stored fact under the key is secret.
  - `apply_save_as_myth` renamed-key rule, in addition to today's key match: a proposed fact counts as flagged when its normalised key is **not** a key of `before` **and** some `conflict`/`retcon` flag's `new_fact` normalises to `norm(value)` or `norm(f"{key}: {value}")`, **or** some `retcon` flag with `new_fact is None` (a removed key) exists and the fact's normalised value differs from every stored value under that removed key. Flagged keys of `before` are restored as today.
  - `merge_proposals(left, right)`: for an incoming proposal with `entry_id is not None` and a different pending proposal with the same `entry_id`, replace that one **in place**, keeping its `proposal_id`. The same-id replacement and `{"clear": [...]}` behave as today.
  - `create_or_update_entry` gains `pending: Annotated[list, InjectedState("pending_proposals")]`. When an update/delete targets an `entry_id` that already has a pending proposal **in state** (an earlier step), the Command also carries `"check_results": {<old proposal_id>: None}` so the replaced proposal is re-checked.
  - `GET /api/threads?pending=<bool>&world_id=<id>` → list of `{thread_id, world_id, pending: int, created_at: str, kind: "chat", title: str | None, badge: Badge | None}`, newest first.
    - `world_id` filters through `ThreadRegistry.list(world_id)`; unknown world → `[]`.
    - `title`: the registry `title` if set, else the first unnamed `HumanMessage` text, one line, cut to 80 characters with `…`; `None` for an empty thread.
    - `badge`: `worst_badge` of the pending checks; `None` when nothing is pending.

- [ ] **Step 1: Write the failing check tests.**
  - `test_retcon.py`:
    - `test_one_retcon_flag_per_stored_fact`: before `Members: About sixty` (canon) and `Members: Ashen Choir` (secret), after `Members: About seventy` → two flags; `existing_fact` values `About sixty` and `Ashen Choir`; `existing_secret` is `False` and `True`.
    - `test_retcon_pure_addition`: before `Moons: One (Ister)`, after `Moons: One (Ister)` and `Moons: Three` → one flag, `new_fact == "Three"`, explanation starts `Adds to established canon`.
    - The existing retcon tests still pass (adjust only those that asserted joined values).
  - `test_myth.py::test_save_as_myth_renamed_key`: before `Moons: One (Ister)`; after `Number of moons: Three`; retcon flag `Removes established canon: One (Ister)` on `Moons` → result has `Moons: One (Ister)` canon and `Number of moons: Three` with status `myth` and the given `told_by`. And `test_save_as_myth_new_unrelated_key_stays_canon`: an added `Weather: Evening sea fog` that equals a stored value of no removed key stays canon.
  - `test_duplicate.py`:
    - `"Captain Sorn Vey"` against an entry `"Captain Sorn"` → one note `Possible duplicate of ent_00NN 'Captain Sorn'` (overlap 2/3); `"Sorn"` against `"Captain Sorn"` → no token-overlap flag (1/2);
    - `"The Harbour Council"` exact title is never reached here (the tool refuses it), but `"Harbour Council Chamber"` against `"The Harbour Council"` → flagged (overlap 2/3);
    - `"Ketra's Lantern"` against the seed → no flag;
    - a secret matching entry gives `existing_secret=True`.
  - `test_contradiction.py::test_create_gets_duplicate_note_without_judge_change`: a fake judge returning no flags; a near-duplicate create → `verdict == "none"` and exactly one `note` flag with the duplicate copy. Also the failed path keeps the duplicate note.
  - `test_badge.py`: one case per row of the precedence list, `worst_badge([])` is `None`, and `worst_badge(["note", "possible"]) == "possible"`.
- [ ] **Step 2: Write the failing graph, state and route tests.**
  - `test_merge_proposals_replaces_same_entry`: left `[p1(entry ent_0002)]`, right `[p2(entry ent_0002)]` → one proposal, `proposal_id == p1.proposal_id`, `after == p2.after`. Creates (`entry_id None`) never collapse.
  - `test_same_entry_proposals_collapse_to_one_card` (graph, scripted agent): one AI message with two `create_or_update_entry` update calls on `ent_0002` → the interrupt lists one proposal whose `after` is the second call's.
  - `test_failed_check_copy_is_one_constant`: `nodes._failed_result(p).flags[0].explanation == CHECK_FAILED_EXPLANATION`.
  - `test_list_threads_scoped_by_world`: two worlds, one pending thread each → `?pending=true&world_id=velmar` returns only Velmar's, with `title` from the first author message and `badge` set; `?world_id=nope` → `[]`.
  - `test_pending_payload_gets_badges_for_old_checkpoints`: a thread paused at the gate → `GET /threads/{id}` has `pending_interrupt.checks[pid].badge`; the SSE `interrupt` event dict has it too.
- [ ] **Step 3: Run** `cd api && uv run pytest -q`. Expected: the new tests FAIL; everything else passes.
- [ ] **Step 4: Implement** the Interfaces above.
- [ ] **Step 5: `docs/requirements.md`.** Decision log rows (2026-11-06): "One retcon flag per stored fact, so a flag never mixes a secret with a canon value (M1 review M3)"; "Badges are derived from the check result at the API edge (`check/badge.py`), not stored, so old checkpoints show them"; "Save as myth also marks a renamed key's new fact as myth". R19.1: add the `world_id` parameter and the new list fields. R12.9: replace "Until Review and Import are built (M2), only Canon and Chat are shown" with "Import is shown from Wave 5".
- [ ] **Step 6: Run** `cd api && uv run pytest -q`. Expected: all pass (389 + new).
- [ ] **Step 7: Commit** as `feat: per-fact retcons, duplicate notes, one card per entry, review badges`, with `Closes: #41`.

---

### Task 2: Card upgrades (#42)

**Builder: Opus** (secret masking in new rows).

**Files:**
- Create: `web/lib/factRows.ts`, `web/lib/review.ts`, `web/components/DiffView.tsx`, `web/tests/factRows.test.ts`, `web/tests/DiffView.test.tsx`
- Modify: `web/components/FactTable.tsx`, `web/components/ApprovalCard.tsx`, `web/components/ChatThread.tsx` (import `checkSummary` from `lib/review.ts`), `web/lib/types.ts`, `web/lib/useAgentStream.ts` (`detailOf`), `web/package.json` (`"diff": "9.0.0"`), `api/sagaloom/graph/nodes.py` (`_parse_decisions` names the field)
- Test: `web/tests/ApprovalCard.test.tsx`, `web/tests/useAgentStream.test.tsx`, `api/tests/graph/test_graph.py`

**Interfaces:**
- Consumes: `CheckResult.badge` and the per-stored-fact retcons from Task 1.
- Produces:
  - `types.ts`: `export type Badge = "conflict" | "failed" | "possible" | "retcon" | "note" | "clear"`; `CheckResult.badge?: Badge` (optional only for type safety; the API always sends it); `ThreadSummary` gains `created_at: string`, `kind: "chat" | "import"`, `title: string | null`, `badge: Badge | null`.
  - `lib/review.ts`:
    - `BADGE_LABEL: Record<Badge, string>` (`clear` → `"Clear"`), `BADGE_CLASS: Record<Badge, string>` (Global Constraints table);
    - `badgeOf(check: CheckResult): Badge` returns `check.badge`, falling back to the same precedence as the server when absent;
    - `checkSummary(p: PendingInterrupt)` moved here unchanged from `ChatThread.tsx`;
    - `proposalSummary(p: Proposal, c: CheckResult, secret: (f: Flag) => boolean): string`: the first conflict, else retcon, flag with a key → `"<key>: <existing> → <new>"` (`→ removed` when `new_fact` is null; `"a secret fact"` in place of a masked value); else a duplicate note's explanation; else `"Deletes this entry · <n> entries mention it"` for deletes; else `"No conflicts found"`.
  - `lib/factRows.ts`:
    - `type FactResult = "Matches" | "Changed (retcon)" | "Changed" | "Conflict" | "Possible conflict" | "Note" | "New" | "Removed"`
    - `interface FactRow { key: string; canon: Fact[]; proposed: Fact[]; result: FactResult; flags: Flag[]; cite?: { id: string; title: string } }`
    - `buildFactRows(p: Proposal, c: CheckResult): FactRow[]`:
      - **update:** one row per normalised key over `before.facts` then new keys from `after.facts` (first-seen order), `canon`/`proposed` = that key's facts on each side, `flags` = flags whose normalised `fact_key` matches and whose `entry_id` is the proposal's entry or any other entry. Then one extra row per flag with a key whose normalised key matches no fact on either side.
      - **create:** one row per flag with a `fact_key` (today's rows), `canon` empty, `cite` = the flagged entry.
      - **delete:** `[]`.
      - `result` precedence: any hard `conflict` → `Conflict`; any `conflict` → `Possible conflict`; any `retcon` → `Changed (retcon)`; any `note` → `Note`; key only in `after` → `New`; only in `before` → `Removed`; same normalised value sets → `Matches`; else `Changed`.
    - `lineDiff(before: Entry, after: EntryDraft): { field: "title" | "type" | "status"; old: string; new: string }[]` — only fields that changed.
  - `FactTable({ rows, secretOf, typeOf })`: columns **Fact | In canon | Proposed | Result**. Each value renders through `SecretValue`. A conflict row cites the other entry with `Cite` in the In canon cell. Under each row with flags: each flag's explanation and, when present, `Suggested fix: <text>`, both through `SecretValue` with the flag's masking (R4.5: per flag, not pooled).
  - `DiffView`:
    - `LineDiff({ changes })`: old struck through (`line-through text-muted-foreground`), new highlighted (`text-foreground` on `bg-accent/15`).
    - `BodyDiff({ before, after, secret })`: a `<details>` "Body changes", `open` when the bodies differ, omitted when equal; words from `diffWords`, added in `<ins>`, removed in `<del>`; when `secret`, the whole diff sits behind one Show button.
  - `ApprovalCard`: header badge list from `badgeOf` + flag kinds (a card can show Retcon and Note together, as today), with `possible` reading "Possible conflict"; the pooled "Suggested fix" blocks at the bottom are removed (each fix is under its row); prose flags keep today's quote layout plus their fix; on updates the `LineDiff` and `BodyDiff` sit above the table and the "Facts to commit" list is dropped (the table is complete); creates and deletes render as today apart from badges and per-flag fixes.
  - `EditForm`: `maxLength` 120 (title), 4000 (body), 40 (fact key), 200 (fact value); told-by input keeps 120.
  - `detailOf` in `useAgentStream.ts`: a list-shaped FastAPI `detail` becomes `"<field>: <msg>"` joined by `"; "`, where field is the `loc` path without `body`, `decisions` and numeric indexes (e.g. `edited.title: String should have at most 120 characters`).
  - `_parse_decisions`: `Invalid decision (<loc joined by ".">): <msg>`.

- [ ] **Step 1: Install** `cd web && pnpm add diff@9.0.0`. Check `web/package.json` shows `"diff": "9.0.0"`.
- [ ] **Step 2: Write the failing tests.**
  - `factRows.test.ts`, with the seed's Harbour Council (`Seats: Seven`, `Meets at: The Tidehall`, `Chaired by: Mayor Elsbeth Varr`) updated to `Seats: Five`, a retcon flag on Seats and a hard conflict on Seats from `ent_0011`:
    - three rows in stored order; Seats → `Conflict` (precedence over the retcon) with both flags; Meets at and Chaired by → `Matches`;
    - without the conflict flag, Seats → `Changed (retcon)`;
    - an added `Motto: Salt and tide` → `New`; a dropped fact → `Removed`; a changed myth value → `Changed`;
    - a create with one conflict flag → one row with `cite`; a delete → `[]`;
    - `lineDiff` reports only `status` when only the status changed.
  - `ApprovalCard.test.tsx`:
    - `shows the complete table on an update`: four column headers, a `Matches` cell, and `Suggested fix:` under the Seats row (not at the card bottom).
    - `labels a possible conflict`: a `possible`-severity conflict shows `Possible conflict`, not `Conflict` (update the existing `Conflict` assertions only where the fixture is `possible`).
    - `masks own secret facts in the complete table`: Mayor Elsbeth Varr update → the `Sings with the Ashen Choir` value is hidden behind Show.
    - `masks only the secret retcon row`: two retcon flags (canon and secret) → one masked cell.
    - `masks the body diff of a secret entry`: a secret entry's body change shows Show, not the words.
    - `no apply-fix button`: no button whose name matches `/apply/i`.
    - `edit form mirrors the schema limits`: title input `maxLength` 120, body 4000, fact key 40, value 200.
  - `DiffView.test.tsx`: `BodyDiff` marks `seven` in `<del>` and `five` in `<ins>`; equal bodies render nothing; `LineDiff` strikes the old title.
  - `useAgentStream.test.tsx::shows field names for a 422 list detail`: a mocked `/decisions` 422 with `detail=[{loc:["body","decisions",0,"edited","title"], msg:"String should have at most 120 characters"}]` → `error` contains `edited.title: String should have at most 120 characters`.
  - `test_graph.py::test_invalid_decision_names_field`: resume with an edit whose `edited.title` is 121 characters → the re-asked interrupt's `error` starts `Invalid decision (edited.title)`.
- [ ] **Step 3: Run** `cd web && pnpm vitest run` and `cd api && uv run pytest -q`. Expected: the new tests FAIL.
- [ ] **Step 4: Implement** the Interfaces above. Ruling for the decision log: "`Changed` (no flag) marks a changed myth or rumour value: beliefs never raise a retcon, but the table still shows the change."
- [ ] **Step 5: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build` (lint can take over 2 minutes) and `cd api && uv run pytest -q`. Expected: all green.
- [ ] **Step 6: Commit** as `feat: approval card shows old vs new, severity and per-flag fixes`, with `Closes: #42`.

---

### Task 3: Review tab (#43)

**Builder: Sonnet.**

**Files:**
- Create: `web/app/review/page.tsx`, `web/app/review/[threadId]/page.tsx`, `web/components/ReviewList.tsx`, `web/components/ReviewDetail.tsx`, `web/components/ReviewQueue.tsx`, `web/tests/ReviewList.test.tsx`, `web/tests/ReviewDetail.test.tsx`
- Modify: `web/components/Header.tsx`, `web/lib/api.ts`, `web/lib/useAgentStream.ts`, `web/app/chat/page.tsx`
- Test: `web/tests/useAgentStream.test.tsx`, `web/tests/ChatPage.test.tsx`

**Interfaces:**
- Consumes: `GET /threads?pending=true&world_id=` (Task 1); `badgeOf`, `BADGE_LABEL`, `BADGE_CLASS`, `proposalSummary` (Task 2); `ApprovalCard` with `chosen`/`onUndo`.
- Produces:
  - `api.ts`: `getReviewThreads(worldId: string) => request<ThreadSummary[]>("/threads?pending=true&world_id=<enc>")`. `getPendingThreads` is removed; `/chat` uses `getReviewThreads(world.id)` and takes the first row.
  - `REVIEW_KEY = (worldId: string) => ["review", worldId] as const`, exported from `lib/review.ts`.
  - `useAgentStream(threadId, opts?: { autoSubmit?: boolean })`: default `true` (chat unchanged). With `false`, `choose` only records. New `chooseMany(decisions: Decision[])` records several at once (for the bulk buttons). `run()`'s end invalidates `["review"]` (prefix) for both message and decision turns.
  - Header: tabs Canon, Chat, **Review**. The Review tab shows a count pill (sum of `pending` over `getReviewThreads(world.id)`), `refetchInterval: 15000`, hidden when 0. Pill colour as the mockup (`text-conflict` on `bg-background`).
  - `/review` (`ReviewList`): `h1` "Review"; one link row per thread to `/review/<id>`: badge, title (`Untitled chat` when null), `Chat` kind label, `<n> proposals`, relative created time. Empty state copy from Global Constraints.
  - `/review/[threadId]` (`ReviewDetail`), per the mockup:
    - left `aside` "Pending proposals": `h1` "Review", the lead copy, the bulk buttons, then `ReviewQueue` rows (button per proposal: badge, action label, title, `proposalSummary`; `aria-current` on the selected one; a check mark when chosen);
    - right: the selected `ApprovalCard` with `chosen`/`onUndo`, then `Submit <n> decisions`, enabled only when every pending proposal has a choice; it calls `decide`;
    - "Approve <n> with no issues" pre-fills `approve` for proposals whose `check.verdict === "none"` and `check.flags.length === 0` and whose action is not `delete`; hidden when n is 0. "Reject all" pre-fills `reject` on all. Both only fill unchosen cards, and every pre-fill can be undone by the card's Change button before submit;
    - while streaming: the cards are disabled and a status line says `Sending your decisions…`;
    - after the turn: if the thread has a new interrupt (an edit or Save as myth re-check), show it as the new queue; otherwise show the turn's `review` messages as a list, a link `Back to Review`, and a link `Open in Chat` to `/chat/<id>`;
    - the import provenance line ("From <file>" plus the excerpt's first line) arrives with imports in Wave 5; nothing for it here;
    - a thread from another world, or with nothing pending on first load: `This conversation has nothing waiting for review.` plus `Back to Review`.

- [ ] **Step 1: Write the failing tests.**
  - `useAgentStream.test.tsx`: `autoSubmit false records without sending` (no fetch to `/decisions` after choosing every card); `chooseMany records several`.
  - `ReviewList.test.tsx`: renders two rows with badge labels and links; empty state copy; a `null` title shows `Untitled chat`.
  - `ReviewDetail.test.tsx` (mock `useAgentStream`):
    - `Approve 1 with no issues` with one clean and one conflict proposal → `chooseMany` called with one `approve`;
    - `Reject all` → `reject` for both;
    - `Submit 2 decisions` is disabled until both are chosen, then calls `decide` with both;
    - `shows the re-asked card after a myth decision`: after `done`, a new `pending` with one proposal renders its card, not the outcome view;
    - outcome view lists the review notes and both links.
  - `ChatPage.test.tsx`: `/chat` calls `getReviewThreads(<world id>)`.
  - Header test (in an existing or new file): the Review tab shows `3` for threads with 2 + 1 pending, and no pill for 0.
- [ ] **Step 2: Run** `cd web && pnpm vitest run`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the Interfaces above. Keep `ApprovalCard` untouched apart from props it already has.
- [ ] **Step 4: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build`. Expected: all green.
- [ ] **Step 5: Commit** as `feat: Review tab with queue, bulk actions and one submit`, with `Closes: #43`.

---

### Task 4: False-alarm eval, Wave 4 demo, docs (#44)

**Builder: Sonnet.**

**Files:**
- Modify: `api/tests/eval/test_check_eval.py`, `web/e2e/exit-demo.spec.ts`, `web/e2e/README.md`, `README.md`, `docs/review-notes.md`, `docs/requirements.md`

**Steps:**

- [ ] **Step 1: R4.10 eval** `test_consistent_proposals_rarely_hard` in `test_check_eval.py`, on the shared loop, in an isolated copy of the Velmar seed:
  - 10 proposals that agree with the seed (listed in the test with one comment each saying why it is consistent): 5 creates of new entries that mention seed entries consistently (e.g. a lamplighter's apprentice on Lantern Quay, a Salt Guild ledger) and 5 updates that add new facts without changing stored ones (e.g. Lantern Quay `Paving: Grey cobbles`).
  - Run `check_proposal` once per proposal with the real judge. Assert the total of `severity == "hard"` conflict flags is `<= 1`; print each flag.
  - If it fails, tune `check/prompts.py` only, then re-run `test_scripted_contradictions_caught` (R4.9 / R11.3.8) and record both results in the issue.
- [ ] **Step 2: e2e timing minors** in `exit-demo.spec.ts`:
  - `rejectAll`: after each click, wait for **either** the card count to drop **or** an error alert in the thread, with `expect.poll` or `Promise.race` on two `expect`s; an alert fails at once with its text. Keep waiting on the card **count** (the Wave 3 rule: no timing-based waits).
  - After a decision, call `settle(p)` before counting again, so a re-asked card (1→0→1) is counted.
- [ ] **Step 3: Wave 4 demo step** (spec §2 Wave 4 demo, adjusted: Captain Sorn is already committed in step 4, so the new character is Mira Hale):
  1. In Chat, send `Add Mira Hale, a harbour pilot who guides ships past the Drowned Bell, and make the Harbour Council five members.`
  2. Open the Review tab. Its pill shows at least `2`. Open the thread's row.
  3. Two queue rows. The Harbour Council card has the table with a `Seats` row whose Result is `Conflict` or `Changed (retcon)`, and the other rows `Matches`; the line diff or body diff is visible if the body changed.
  4. Click `Approve 1 with no issues` if shown, else choose Approve on Mira Hale; Reject the council change; `Submit 2 decisions`.
  5. The outcome lists one `committed as ent_` and one `rejected`; the Review pill is gone (count 0).
  - If the agent asks a question instead of proposing, the step fails with the agent's reply printed. If a run fails, copy `test-results/` before re-running.
- [ ] **Step 4: README.**
  - Walkthrough "Review tab": the demo above, why one submit per batch (one `interrupt()` per batch, R18.5), what each badge means, and that fixes are guidance only.
  - Update the approval-card walkthrough for the complete table and the diffs.
  - Limitations: Save as myth links a renamed key only by value; a duplicate note is a hint, merging is M3.
- [ ] **Step 5: Review notes (R17.6):** why badges are derived at the API edge; why the table is complete on updates only; why the replacement lives in the reducer (parallel tool calls share one state).
- [ ] **Step 6: Run every suite and eval:**
  - `cd api && uv run pytest -q`
  - `cd web && pnpm vitest run && pnpm lint && pnpm build`
  - `cd api && uv run pytest -m eval -v -s`
  - `cd web && pnpm exec playwright test` (then check nothing listens on 8100 or 3100)
  - Expected: all green; quality evals ≥9/10; security evals complete passes; R4.10 ≤1 hard flag. Report any failure per case; don't tune anything except as Step 1 allows.
- [ ] **Step 7: Check the docs against the code**: every number, endpoint, copy string and setting name in the diff.
- [ ] **Step 8: Commit** as `docs: Wave 4 Review walkthrough, demo and false-alarm eval`, with `Closes: #44`.

After Task 4: run the Fable whole-wave review (fixes in #45 in both repos, with an Opus re-review), confirm with the user, push `main` to both remotes, archive the ledger and reviews to `internal docs/m2/<time>-wave4-*.md`, and update the handoff.
