# Sagaloom M3 Wave 2: Web Clean-up — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every web-side item of the M3 inventory (design §4.2, plus the web items its sources rule M3) is fixed or closed by a written ruling, so the web app carries no known debt into Wave 3.

**Architecture:** No new features. One secret rule, now read through one stored-aware helper on every proposal surface; the Edit form stops putting hidden values in the DOM; one Show per secret entry. The rest is tidy-up by file area: the review lib and page, the proxy and type tooling, the secret store and drawer mask, text matching and colour tokens, polling, Studio and memory panels, and the Import page. Three items in §4.2 touch API code (flagged per task). The graph and the SSE event set do not change.

**Tech Stack:** Next.js 16 + React 19 + TanStack Query 5 + vitest (web/, `pnpm`), FastAPI + LangGraph (api/, `uv`), Playwright.

> **Line references** are as of `2eb86ea`. Earlier M3 waves shift them, so re-locate by symbol before editing.

**Spec:** `docs/superpowers/specs/2026-11-09-2041-sagaloom-m3-design.md` §4.2, with §2, §6, §7, §8. Findings come from `internal docs/m2/*-wave{1,2,3,4,5,7,8}-*.md` and the "Carried to M3" list in `docs/superpowers/plans/2026-11-09-1527-sagaloom-m2-wave8-hardening.md`.

## Rulings (made in this plan)

1. **Show buttons on a secret entry's card follow ruling R5 of Wave 8** (pending Open question 1): the card header's **Show** is the one reveal for the entry; it lifts the title, the body and every fact hidden *because the entry is secret*. A fact that is secret in its own right keeps its own Show. The proposal's own citations (retcon `Cite`) have no Show of their own. This is the rule the Edit form's **Show to edit** already follows.
2. **The Edit form's hidden fact row follows Show to edit:** its value is unbound like its key (disabled, empty, placeholder), and its status select is disabled until the row is revealed. Not a product question: Wave 8 decision 4 already said a hidden secret is not edited without a reveal.
3. **"Stored-aware" is the one predicate for "this proposal's entry is secret"**: `before`, `after`, or the stored entry in canon (M8). Card header, create block, own citations, Edit form and queue row all read it.
4. **Delete wording:** the queue line says "N entries depend on it" (M10). On the card, while the world shows secrets, link-only dependents are listed under their own line "These entries link to it:" instead of under "These entries mention it:" (the W8 T5 deferred copy item).
5. **Header pill polling** (§8 builder's call): poll every 5 s while a listed thread is `running`, else every 60 s; TanStack's refetch on focus/visibility and the existing `["review"]` invalidations after this tab's own turns and imports stay. Header and Review list share the rule (they share the query key, and TanStack polls at the shortest interval of its observers). Recent imports use the same rule on their own key.
6. **"Found 1 candidate" stays singular.** Same reasoning as Wave 4 ruling R13 ("1 proposal"); the test pins it. Closed as Fine in its issue.
7. **Web minors ruled "Wave 8" that never reached the Carried-to-M3 list are included** (design §1: "the whole list", §2: "nothing stays"): Wave 1's Settings/Studio nits (Reset to default, disabled Save reason, loading anchor, wrapper div, Guardrails toggle test, `["settings"]` prefix match, `courseNotes` fallback) and Wave 4's fact-table rows not grouped by key. The user may strike them; they sit in their own steps.
8. **Reopened from the Wave 8 T5 "Fine" group because the files are touched anyway:** the redundant `byId` term in `storedSecret` (Task 1), the `colorTokens` side-colour false positive and the `undefinedTokens` export from a test (Task 5). `find_mentions(links=True)` is API and stays in Wave 1 (§4.1).
9. **Studio "Try it" for the reference tool is fixed in the product, not only documented.** The Wave 2 ledger ruled it "docs: the link only pre-fills the question". README :132 already says Try it fills the composer; what is still wrong is that the reference card's prompt is only the question, so following it never shows the **Source: reference (Wikipedia)** line that Hard 5 demonstrates. The prompt becomes walkthrough 8's one message (Task 7). Cost if wrong: a Try-it click on that card now ends in a proposal card, which the author rejects.
10. **A delete card's dependents while canon failed to load stay masked until the world toggle** (#60 deferred minor): Fine. A failed load is an error state, fail-closed is the rule, and the toggle is the reveal. Recorded in #79.

## Open questions for the user (one at a time)

**Answered 2026-11-09:** Question 1 → **(b)**, one Show per entry, with own-secret facts keeping their Show (Ruling 1 stands). Question 2 → **(c)**, names and aliases under 4 characters match case-sensitively (Task 5 Step 4, option (c)).

1. **Show buttons on a secret create card** (today four or more; two share the name "Show secret entry").
   - (a) One card-level Show reveals everything, including facts secret in their own right (like a spoiler block that opens whole in Discord or Reddit).
   - (b) **Recommended, and planned:** one Show for the entry; a fact secret in its own right keeps its own Show (what Sagaloom's own Edit form does since Wave 8 R5).
   - (c) Keep a Show per value (like a password manager's per-field eye icon) and only give the own-citation button a distinct name.
2. **Entity chips for 3-character names and aliases** (`MIN_NAME = 3` in `web/lib/mentions.ts`; Wave 7 T5, Fable: "revisit with real aliases").
   - (a) Keep 3 and record it as Fine, with a README limitation line ("a 3-letter alias can chip a common word").
   - (b) Raise to 4.
   - (c) Keep 3 but match names under 4 characters case-sensitively (as typed in the entry).
   Comparable tools: Obsidian's unlinked mentions match a note's title at any length; World Anvil and Kanka avoid the problem by linking only explicit `@` mentions. Task 5 Step 4 implements the answer; (a) needs no code.

Not reopened (never ruled by a review, so not M3 debt): `useAgentStream`'s `restore()`/`reconnect()` have no request timeout (Wave 4 T3 re-review, out-of-scope observation). Raise it with the user only if they want it.

Already done (close in the issue, no work): `ago` is tested (`web/tests/time.test.ts`, W4 T3 nit).

## Global Constraints

- Work goes on `main`. Every commit has `Refs: #N`; the last commit of an issue has `Closes: #N`. End every commit with `Co-Authored-By: Claude <model> <noreply@anthropic.com>` (`Claude Sonnet 5.5` or `Claude Opus 5.5`, the task's builder).
- Issues in both repos, milestone "M3", body sections Aim / What was done / Success criteria / Status / Reviews / Requirements / Commits: **#69** (docs: design and the three wave plans, already decided), **#79–#86** Tasks 1–8, **#87** Fable wave-review fixes. Placeholders: the user renumbers.
- Never read or print `api/.env` or `web/.env.local`. Never call Gemini or any real model, except the exit demo in Task 8, which uses only models in `api/sagaloom/allowed_models.json`.
- The SSE event set does not change: `token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`.
- The secret rule stays one rule everywhere: hidden when `secret && !worldShown && !locallyRevealed`, where `worldShown` comes from the content's world (`useWorldShowSecrets()` under `SecretsWorldProvider`), not the picker's.
- A clean-up changes no user-visible behaviour beyond what its item names (design §2 anti-goal); copy is written in the app's plain style.
- Wave 1 runs first. This wave regenerates no API types unless a task changes an API model (none does); `pnpm types:check` must pass in every task.
- Verification for every task: `cd api && uv run pytest -q`; `cd web && pnpm vitest run && pnpm lint && pnpm build` (lint needs a timeout over 2 minutes); `pnpm types:check` at the repo root. From Task 3 on, `pnpm vitest run` also type-checks `tests/**/*.test-d.ts`. The exit demo (`web/e2e/exit-demo.spec.ts`, real calls) runs once, in Task 8.
- Records: `internal docs/m3/YYYY-MM-DD-HHMM-m3-wave2-*.md`.

## Review Focus

1. **A hidden secret on the Edit form leaves nothing in the page, and submitting without a reveal changes nothing hidden.** With secrets hidden, a secret fact's value appears nowhere in `container.innerHTML` and no input has `type="password"`; on submit every never-revealed row comes back exactly as drafted (Task 1 tests `edit form puts no hidden value in the DOM`, `submitting without Show keeps hidden facts exactly`).
2. **An entry that turned secret after its proposal was drafted.** Canon holds it as secret while `before` and `after` do not: header, create block, own citation, queue row and Edit form all hide it (Task 1 test `a stored secret hides the card and the queue row`).
3. **Session storage that starts failing.** Toggle on, then `setItem` throws while turning it off: the toggle reads off (fails closed), for both secrets and course notes (Task 4 tests `turning secrets off while storage fails reads off`, `course notes follow the last write while storage fails`).
4. **The proxy when the browser's body can't be read, or the API is down.** A body-read failure answers 400 JSON, not "The API is not reachable"; a real fetch failure answers 502 JSON and logs its cause once, without the shared secret in the log (Task 3 tests).
5. **The pill after a decision or an import in this tab.** It updates at once through the `["review"]` invalidation, even while the interval is 60 s (Task 6 test `pill updates after a decision without waiting for the interval`).

---

### Task 1 (#79): Secrets on the approval card, the queue row and the Edit form

Builder: **Opus 5.5** (secrets UI).

Items: W8 M9 (both halves), W8 M8, W8 M10, W7 four Show buttons and two "Show secret entry" buttons, W8 T5 link-only refs under "mention it", W8 T5 redundant `byId` term, W4 T3 `byId` built twice, W7 M12 web gaps and #60 deferred test minors.

**Files:**
- Modify: `web/components/ApprovalCard.tsx` (`ApprovalCardBody` :59–322, `DeleteDependents` :331–369, `EditForm` :384–520), `web/components/FactList.tsx` (`hideAll` :79–108), `web/components/FactTable.tsx` (`Cite` :11–50, `SecretValue` :56–94), `web/components/ReviewQueue.tsx` (:34), `web/lib/review.ts` (`secretIndex` :152–158, delete line :143–147)
- Modify docs: `README.md` (:126 walkthrough bullet; delete the limitation at :250), `docs/review-notes.md` (:161 drop "Known limits"), `docs/requirements.md` (R11.2.8 card copy at :264)
- Test: `web/tests/ApprovalCard.test.tsx`, `web/tests/ReviewQueue.test.tsx`, `web/tests/review.test.ts`, `web/tests/EntryView.test.tsx`

**Interfaces:**
- Produces (in `web/lib/review.ts`):
  - `entryIndex(proposal: Proposal, canon: Entry[] | undefined): { byId: Map<string, Pick<Entry, "status" | "facts" | "type" | "title">>; unknown: (id: string) => boolean }` — today's private `secretIndex`, exported and widened; `existingSecretOf`, `textSecretOf` and `ApprovalCard` all use it (no second `byId`).
  - `entryIsSecret(proposal: Proposal, canon: Entry[] | undefined): boolean` — `before` or `after` has status `secret`, or `canon` holds `proposal.entry_id` with status `secret`.
  - `proposalSummary` delete line: `Deletes this entry · 1 entry depends on it` / `Deletes this entry · N entries depend on it`.
- `SecretValue` and `Cite` gain `revealable?: boolean` (default `true`); `false` renders the mask with no Show button.
- `FactList`'s `hideAll` now means "hidden for the entry's sake": those rows render no per-row Show. Rows secret in their own right keep theirs once `hideAll` is false.
- `ApprovalCardBody`: `entryHidden = entryIsSecret(proposal, canon) && !worldShown && !entryRevealed`; header chip, region name, create-block title and body (`revealable={false}`), own `Cite` (`revealable={false}`) and `FactList hideAll` all read it. `EditForm` gets `secretEntry={entryIsSecret(proposal, canon)}`.
- `EditForm` hidden row: value input `disabled value="" placeholder="Secret fact"` (same `aria-label`), status select `disabled`; nothing hidden is bound to its text. `submit` sends every never-revealed row exactly as drafted (no trim, no empty-row filter); revealed and visible rows keep today's trim and filter.
- `DeleteDependents` while shown: text refs under "These entries mention it:", link-only refs under "These entries link to it:". Hidden-state copy unchanged (`and 1 linked entry`, `1 linked entry depends on it`).

- [ ] **Step 1: Failing tests** in `ApprovalCard.test.tsx`:
  - `edit form puts no hidden value in the DOM` (secret fact `Holder: Yes, at every full Ister`, world hidden: `container.innerHTML` does not contain the value; `container.querySelector('input[type="password"]')` is null; after `Show secret fact 1` the value input holds it).
  - `edit form locks a hidden row's status` (`Fact 1 status` is disabled while hidden, enabled after its Show).
  - `submitting without Show keeps hidden facts exactly` (submit unrevealed: `edited.facts` equals the draft's facts, key, value, status and `told_by` included).
  - `a stored secret hides the card and the queue row` (`before.status = "canon"`, `canon` holds the entry as `secret`: no title text in the card; queue row reads `Secret entry`).
  - `one Show reveals a secret create` (secret create with one canon-status fact and one secret fact: exactly one button named `Show secret entry`, no `Show secret fact` before it; after it, title, body and the canon-status fact show, and exactly one `Show secret fact` remains).
  - `own citation has no Show of its own` (the retcon fixture of the existing "own title in a retcon citation" test: one `Show secret entry` button in the card, and `within(citation)` shows the title after it).
  - `own prose-flag citation hides with the entry` (keyless flag citing `proposal.entry_id`: title absent until the card's Show; the #60 untested path).
  - `delete card lists link-only dependents on their own line while shown` ("These entries link to it:" precedes `Mayor Elsbeth Varr`).
  - Tighten the existing "≥2 occurrences" assertion in the retcon-citation test to `within(<citation>)`.
- [ ] **Step 2:** In `review.test.ts`: `delete summary says depend on it` (1 and 3 dependents). In `ReviewQueue.test.tsx`: the stored-secret row case. In `EntryView.test.tsx` (W7 M12): `a locally revealed secret entry still masks a secret ref` (reveal the page's entry, its fact refs a second secret entry: `Secret entry`, not that title).
- [ ] **Step 3:** Run `cd web && pnpm vitest run tests/ApprovalCard.test.tsx tests/ReviewQueue.test.tsx tests/review.test.ts tests/EntryView.test.tsx`; the new cases fail.
- [ ] **Step 4:** Implement the Interfaces above. Update the existing tests that click per-value Shows on a secret entry's card to the one header Show; change no assertion about what is hidden.
- [ ] **Step 5: Docs.** Delete README's "Hidden facts are still in the page." limitation (:250). README :126 and review-notes :161: say a hidden fact row carries no value and its status is locked until its Show, and that a secret entry's card has one Show. R11.2.8's card copy names both lines.
- [ ] **Step 6:** Full verification (Global Constraints). Commit:

```bash
git commit -m "fix: hidden Edit rows carry no value; one Show per secret entry; stored-aware card secrecy

Refs: #79
Closes: #79
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2 (#80): Review lib and page tidy-ups

Builder: Sonnet 5.5.

Items: W4 M3 `setHeld` during render, (W4 M9 parallel-collapse `ToolMessage` id moved to M3 Wave 1 Task 2, by Wave 1 ruling R2), W4 M10 / T3 `CHECK_FAILED_TEXT`, W4 T2 `norm` into `lib`, W4 T3 error paragraph repeated, W4 T3 Header test reads the cache a tick early, W4 wave-fix keyless-conflict queue test, W4 T2 fact-table extra rows not grouped by key (Ruling 7).

**Files:**
- Create: `web/lib/text.ts`
- Modify: `web/lib/review.ts` (`norm` :57 moves out; gains `CHECK_FAILED_TEXT`), `web/lib/factRows.ts` (:1 import, grouping in `buildFactRows`), `web/components/ApprovalCard.tsx` (:15 constant moves out), `web/components/ReviewQueue.tsx` (:1 import), `web/lib/useAgentStream.ts` (`decide` :349, `setPending` :136, `AgentStream`), `web/components/ReviewDetail.tsx` (:55–73, the error paragraphs :111, :135, :180, :241)
- Test: `web/tests/factRows.test.ts`, `web/tests/useAgentStream.test.tsx`, `web/tests/ReviewQueue.test.tsx`, `web/tests/Header.test.tsx`

**Interfaces:**
- Consumes: Task 1's `lib/review.ts` (same file, sequential).
- Produces: `web/lib/text.ts` exporting `norm(s: string): string` (body unchanged); `CHECK_FAILED_TEXT` exported from `web/lib/review.ts`; `AgentStream.sent: { pending: PendingInterrupt; chosen: Record<string, Decision> } | null` — set inside `decide`'s start callback just before `setPending(null)`, cleared by any `setPending(non-null)`. `ReviewDetail` reads `s.sent` instead of its `held` state.
- `buildFactRows`: flags whose key matches neither side are grouped into one row per `norm(fact_key)` (create and update branches alike).

- [ ] **Step 1: Failing tests.** `factRows.test.ts`: `groups unmatched flags by key` (two flags on `Founded`, absent from both sides → one row, two flags; on a create too). `useAgentStream.test.tsx`: `keeps the sent set until the next interrupt` (`decide` → `pending` null, `sent.pending` the old set; a new `interrupt` event → `sent` null). `ReviewQueue.test.tsx`: `a keyless hard conflict shows its explanation`.
- [ ] **Step 2:** Run the named files; the new cases fail.
- [ ] **Step 3:** Implement. `ReviewDetail` loses `held`/`setHeld` and the render-time `setState`; one local `ErrorLine({ text }: { text: string | null })` renders the four `role="alert"` paragraphs. `Header.test.tsx`: assert the pill inside `waitFor` on the DOM (`findByRole`), not on the query cache.
- [ ] **Step 4:** Full verification. Commit with `Refs: #80`, `Closes: #80`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 3 (#81): Proxy and type tooling

Builder: **Opus 5.5** (the proxy carries the shared secret).

Items: W8 M5, W8 M4, W1–2 `PROXY_PREFIX` duplication (**API constant**), W8 M11, W8 M13.

**Files:**
- Modify: `web/app/api/proxy/[...path]/route.ts` (:23–53), `web/lib/api.ts` (:20), `web/lib/useAgentStream.ts` (:221), `web/lib/useImport.ts` (:62), `web/vitest.config.mts`, `package.json` (root `types:gen`), `scripts/types-check.mjs`
- Create: `scripts/types-gen.mjs`; rename `web/tests/apiTypes.test.ts` → `web/tests/apiTypes.test-d.ts`
- Test: `web/tests/proxy.test.ts`, new `web/tests/proxyPrefix.test.ts`

**Interfaces:**
- Proxy: the body is read before the fetch `try`; a read failure → `jsonError(400, "Could not read the request body")`. Fetch failure → `console.error("proxy: API fetch failed", url, cause)` then `jsonError(502, "The API is not reachable")` (log the target URL and the cause, never the headers). Path guard → `jsonError(400, "Bad path")`.
- `web/lib/api.ts` exports `PROXY_BASE = "/api/proxy"`; `useAgentStream` and `useImport` build their URLs from it.
- `proxyPrefix.test.ts` pins the cross-language copy: `api/sagaloom/tools/export.py`'s `PROXY_PREFIX = "…"` literal equals `PROXY_BASE`, and `web/app${PROXY_BASE}/[...path]/route.ts` exists. (The API constant stays in Python; the test is the single source of agreement, as the judge-prompt fixture is for masking.)
- `scripts/types-gen.mjs` exports `generate(jsonPath: string, tsPath: string): void` (the two `execSync` calls) and, run directly, writes the committed paths. Root `types:gen` becomes `node scripts/types-gen.mjs`; `types-check.mjs` imports `generate`. The command string exists once.
- `vitest.config.mts` `test.typecheck`: `{ enabled: true, include: ["tests/**/*.test-d.ts"] }`, so `pnpm vitest run` fails on a type assertion.

- [ ] **Step 1: Failing tests** in `proxy.test.ts`: `answers 400 JSON when the request body cannot be read` (a `Request` whose `text()` rejects; `fetch` not called); `logs the cause of an unreachable API` (`console.error` spy called once with the `TypeError`; no logged argument contains the shared secret); `answers the path guard in JSON` (status 400, `content-type: application/json`, `{"detail":"Bad path"}`). Add `proxyPrefix.test.ts`. Run them; they fail.
- [ ] **Step 2:** Implement the proxy and `PROXY_BASE`; run `pnpm vitest run tests/proxy.test.ts tests/proxyPrefix.test.ts`.
- [ ] **Step 3:** Typecheck: rename the type test, add the `typecheck` block. Prove it bites: change `toEqualTypeOf<number>()` on `version` to `<string>()`, `pnpm vitest run tests/apiTypes.test-d.ts` exits 1; revert, exits 0. Record both in the issue.
- [ ] **Step 4:** Generator once: add `types-gen.mjs`, point both callers at it. Run `pnpm types:gen` (no diff in `web/lib/openapi.json` or `api-types.gen.ts`), then `pnpm types:check` (exit 0).
- [ ] **Step 5:** Full verification. Commit with `Refs: #81`, `Closes: #81`, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 4 (#82): Secret store and drawer mask internals

Builder: **Opus 5.5** (fail-closed secret masking).

Items: W7 M14 stale `"true"` in `secrets.tsx`, listener sets not pruned, `BLOCK_PARTS`, `argsHoldSecret` string args, Response tab relying on the veil; W7 M12 `read()` stale edge untested and `ChatPage` `getEntries` mock not reset; W1 T4 `courseNotes` fallback half-applied (Ruling 7); W3 T3 `as unknown as LlmResponse` cast.

**Files:**
- Modify: `web/lib/secrets.tsx` (`read`/`write`/`subscribe` :10–39), `web/lib/courseNotes.ts` (`read`/`write` :22–40), `web/lib/maskSecrets.ts` (:7–8, `argsHoldSecret` :55–59), `web/components/UnderTheHood.tsx` (`Response` :106–124 and its caller), `web/lib/turns.ts` (`parseRouterMode`), `web/lib/useAgentStream.ts` (:293)
- Test: `web/tests/secrets.test.ts`, `web/tests/CourseChip.test.tsx`, `web/tests/maskSecrets.test.ts`, `web/tests/UnderTheHood.test.tsx`, `web/tests/turns.test.ts`, `web/tests/ChatPage.test.tsx` (`beforeEach` :42)

**Interfaces:**
- Storage fallback (both stores): the in-memory value is kept **only while the last write to storage failed** and wins over storage while kept; a successful write clears it. So a failed "off" never reads back a stored "on". Cross-tab `storage` events for course notes still work.
- `subscribe` in `secrets.tsx` deletes a world's listener `Set` when it empties.
- `maskSecrets.ts`: `UNTRUSTED` and `BLOCK_PARTS` are both built from one `OPEN_TAG`/`CLOSE_TAG` source. `argsHoldSecret(args: unknown)` parses a string argument as JSON first (an unparsable string holds no secret status).
- `Response({ call, hidden }: { call: LlmCall; hidden: boolean })` passes `hidden` to `callText`; the veil stays as well.
- `parseRouterMode(data: unknown): Mode | null` narrows its input itself; the cast at `useAgentStream.ts:293` goes.

- [ ] **Step 1: Failing tests.** `secrets.test.ts`: `turning secrets off while storage fails reads off` (on with working storage; then `setItem` throws; set off → hook reads `false`); `drops a world's listener set when the last subscriber leaves`. `CourseChip.test.tsx`: `course notes follow the last write while storage fails` (toggle off then on with a throwing `setItem`). `maskSecrets.test.ts`: `a JSON-string args with a secret status is masked`; `an unparsable string args is not`. `UnderTheHood.test.tsx`: `Response masks secret tool-call args while hidden even without the veil` (render `Response` with a call whose request masked nothing and whose reply proposes `status: "secret"`). `turns.test.ts`: `parseRouterMode reads a plain object and rejects junk`.
- [ ] **Step 2:** Run them; they fail. Implement. In `ChatPage.test.tsx`, reset `getEntries` to its default in `beforeEach`.
- [ ] **Step 3:** Full verification (the `test_prompt_fixture.py` cross-language test must stay green). Commit with `Refs: #82`, `Closes: #82`, `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

---

### Task 5 (#83): Entity matching, imported headings and colour tokens

Builder: Sonnet 5.5.

Items: W7 M14 dated-heading regex twice (and `sectionsOf`'s trim), regex built per render, 3-character aliases (Open question 2); W7 M8 hex one-offs; W7 M14 `--failed` under the conflict comment; W8 T5 `colorTokens` side-colour false positive and `undefinedTokens` exported from a test (Ruling 8).

**Files:**
- Modify: `web/lib/imported.ts`, `web/lib/sections.ts` (:14–16), `web/lib/mentions.ts` (`linkEntities` :19–46, `MIN_NAME` :6), `web/app/globals.css`, `web/components/UnderTheHood.tsx` (:39, :182), `web/components/CanonList.tsx` (:87), `web/components/ChatThread.tsx` (:65, :221), `web/components/FeatureMap.tsx` (:8–15), `web/tests/colorTokens.test.ts`
- Create: `web/tests/colorTokenScan.ts` (the scanner, moved out of the test file)
- Test: `web/tests/imported.test.ts`, `web/tests/sections.test.ts`, `web/tests/mentions.test.ts`, `web/tests/colorTokens.test.ts`

**Interfaces:**
- `imported.ts` holds one pattern source for `Imported from <label> (<YYYY-MM-DD>)`; `importedSections`, `isImportedHeading` and `sectionsOf` all use it, and all accept one or more spaces after `##` (so `##  Imported from x (2026-01-01)` counts the same in both).
- `linkEntities` keeps its signature; the name map and regex are cached per `(entries array, showSecrets)` (a `WeakMap` keyed on the array), so a re-render with the same entries builds nothing.
- Hex one-offs become tokens in `globals.css` (`--color-*`, values unchanged, names that say what they colour, e.g. `--color-untrusted-bg`, `--color-call-open-bg`, `--color-row-active`, `--color-user-line`, `--color-hood-bg`, and the four Feature map summary/border shades, all nine literals found in `web/components`). `--failed` moves out from under the conflict-family comment. `mermaid.ts`'s classDef hex stays (Mermaid source, not CSS).
- `colorTokens.test.ts` adds: no class string under `app`, `components`, `lib` uses an arbitrary hex colour (`-[#…]`); side utilities (`border-t-accent`, `border-x-…`) resolve to their colour name.

- [ ] **Step 1: Failing tests.** `imported.test.ts`/`sections.test.ts`: `a double-space imported heading counts in both`. `mentions.test.ts`: `reuses its matcher for the same entries` (through an exported test counter `matcherBuildCount(): number` in `mentions.ts`: two calls with the same array and `showSecrets` add one build; a new array adds another). `colorTokens.test.ts`: `no arbitrary hex colour in class strings` (fails on today's tree, listing the nine sites); `side-colour utilities resolve` (`border-t-accent` passes, `border-t-nope` fails).
- [ ] **Step 2:** Implement; run `pnpm vitest run tests/imported.test.ts tests/sections.test.ts tests/mentions.test.ts tests/colorTokens.test.ts`.
- [ ] **Step 3:** Check by value, not by eye: each new token equals the literal it replaces (list old → new in the issue).
- [ ] **Step 4: Open question 2.** (a): add the README limitation line and close as Fine. (b): `MIN_NAME = 4` plus `mentions.test.ts` `a 3-letter alias is not chipped`. (c): names under 4 characters match case-sensitively; test `a 3-letter alias chips only as written`.
- [ ] **Step 5:** Full verification. Commit with `Refs: #83`, `Closes: #83`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 6 (#84): Header pill polling and the Studio graph

Builder: Sonnet 5.5. **Starts after Wave 1's thread-listing task has landed.**

Items: W4 M5 / M1 M10 pill polling (client half of §4.1's listing item), W3 T4 unknown `?thread=` fires a 404, W1 M7 `["settings"]` prefix match (Ruling 7).

**Files:**
- Modify: `web/lib/review.ts` (new poll helper), `web/components/Header.tsx` (`ReviewCount` :158–176), `web/components/ReviewList.tsx` (:16–21, `badge: null` path :53), `web/components/RecentImports.tsx` (:15–20), `web/components/AgentGraph.tsx` (:11–23), `web/app/studio/page.tsx` (:31), `web/components/SettingsPanel.tsx` (:42), `web/components/GuardrailsPanel.tsx` (:29)
- Test: `web/tests/Header.test.tsx`, `web/tests/ReviewList.test.tsx`, `web/tests/RecentImports.test.tsx`, `web/tests/AgentGraph.test.tsx`, `web/tests/SettingsPanel.test.tsx`

**Interfaces:**
- **Assumed from Wave 1 (check against the Wave 1 plan before starting):** `GET /threads?pending=true&world_id=W` and `GET /threads?world_id=W&kind=import` keep returning `ThreadSummary[]` with `pending`, `approved`, `rejected`, `running` and `badge`, now read from counts kept on the registry row (no `aget_state` per thread). `getReviewThreads`/`getImports` in `web/lib/api.ts` stay as they are. If Wave 1 instead adds a dedicated count route (for example `GET /threads/pending-count?world_id=` → `{ pending: number; running: boolean }`), `ReviewCount` uses it and the rule below is unchanged. **Discriminating check:** `badge` needs a check result, so a registry-row listing may return it as `null` or drop it; `ReviewList` already renders no badge for `null`, and this task adds a test for that row. If the field is dropped, make `ThreadSummary.badge` optional in `types.ts`.
- Produces: `reviewPollMs(rows: ThreadSummary[] | undefined): number` in `web/lib/review.ts` — `5_000` when any row is `running`, else `60_000`. `Header`, `ReviewList` and `RecentImports` pass `refetchInterval: (q) => reviewPollMs(q.state.data)`; focus refetch and invalidations are untouched.
- Settings invalidation uses `{ queryKey: ["settings"], exact: true }` so `["settings", "models"]` is not refetched on a dev-settings save.
- `AgentGraph`: no `getLastRun` until the thread list has loaded; an unknown `?thread=` then falls back to the first thread with no request for the unknown id.

- [ ] **Step 1: Failing tests** (fake timers with `shouldAdvanceTime`). `Header.test.tsx`: `polls every 60 s when nothing runs` (one call at mount; none more at +15 s; a second at +60 s); `polls every 5 s while a thread runs`; `pill updates after a decision without waiting for the interval` (invalidate `["review"]` → a fetch within one tick, the new count shown). `ReviewList.test.tsx`: `a row with no badge still lists`. `AgentGraph.test.tsx`: `an unknown thread param makes no last-run request for it`. `SettingsPanel.test.tsx`: `saving does not refetch the model list`.
- [ ] **Step 2:** Run them; they fail. Implement.
- [ ] **Step 3:** Full verification. Commit with `Refs: #84`, `Closes: #84`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 7 (#85): Studio panels, memory chips and Try it

Builder: Sonnet 5.5.

Items: W3 M6 stale Undo; W3 UI polish (RememberedChip tests in `MemoryPanel.test.tsx`, Delete has no busy state, a live `remember` activity line a reload doesn't show, optional `worldId` prop); W1–2 Studio "Try it" for the reference tool (**API code**); Ruling 7's Wave 1 nits (Reset to default, disabled Save reason, loading anchor, ProvidersPanel wrapper, Guardrails toggle test).

**Files:**
- Modify: `web/components/RememberedChip.tsx`, `web/components/MemoryPanel.tsx`, `web/lib/useAgentStream.ts` (`applyToMessages` `tool_result` :91–99), `web/components/SettingsPanel.tsx` (:120–127), `web/app/studio/page.tsx` (:76–96), `api/sagaloom/studio.py` (`external_tools` `try_href` :203–205)
- Create: `web/tests/RememberedChip.test.tsx` (the chip cases move out of `MemoryPanel.test.tsx`)
- Test: `web/tests/MemoryPanel.test.tsx`, `web/tests/useAgentStream.test.tsx`, `web/tests/SettingsPanel.test.tsx`, `web/tests/GuardrailsPanel.test.tsx`, `api/tests/web/test_studio_routes.py`

**Interfaces:**
- `RememberedChip.undo`: after `forgetMemory`, a string key still present in the returned `preferences` means the Undo was stale: show `Already changed` (role `status`), not `Forgotten`.
- `MemoryPanel`: the row's Delete is disabled with `aria-busy` while its request runs. The `worldId` prop is removed if nothing passes it (grep); otherwise keep it and say why in the issue.
- `applyToMessages`: a `remember` `tool_result` adds only the `memory` message, not a `tool` message, so a live turn shows what a reload shows.
- `SettingsPanel`: **Reset to default** is disabled while `base.settings.agent_system_prompt === null` and resets only the prompt field (unsaved temperature and token edits stay in their inputs); a disabled **Save** shows one line saying why ("Fix the highlighted value" when invalid, "No changes to save" when clean).
- Studio: the loading placeholder carries both `#guardrails` and `#settings` anchors; the empty wrapper `<div>` around `ProvidersPanel` goes.
- `studio.py`: the `external_tools` Try it prompt becomes README walkthrough 8's one message ("What did Byzantine trade routes look like? I want Velmar's harbour to feel like that. Lantern Quay's harbour runs a customs house, like Byzantine ports."), so following it shows the Source line. The e2e `QUESTION` constant is a separate demo step and stays.

- [ ] **Step 1: Failing tests.** First grep for the old Try-it prompt literal (`api/tests/web/test_studio_routes.py`, incl. `test_try_it_links_are_url_encoded`; `web/tests/FeatureMap.test.tsx`) and update any test that pins it. `RememberedChip.test.tsx`: the moved cases plus `a stale Undo says Already changed`. `MemoryPanel.test.tsx`: `Delete is busy while its request runs`. `useAgentStream.test.tsx`: `a live remember result adds no tool line`. `SettingsPanel.test.tsx`: `Reset is disabled on the built-in prompt`; `Reset keeps unsaved temperature`; `a disabled Save says why`. `GuardrailsPanel.test.tsx`: the toggle test also asserts the switch's `aria-checked` flips. `test_studio_routes.py`: `test_reference_try_it_states_a_fact` (the decoded prompt contains "customs house").
- [ ] **Step 2:** Run them; they fail. Implement.
- [ ] **Step 3:** Full verification. Commit with `Refs: #85`, `Closes: #85`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task 8 (#86): Import page, e2e checks, docs and the exit demo

Builder: Sonnet 5.5.

Items: W5 M11 (`done` without `thread_id` copy, `role="status"` on a list, "Found 1 candidate" (Ruling 6), the same file can't be re-chosen, dead 409 copy); W5 M13 web half (`useImport` stream drop and missing `thread_id`, `ImportProgress` untested, empty-file alert unasserted); W5 M10 (page-wide `From paste:`, step 32 skips silently) and W5 T4 e2e README wrapping; docs for the wave; the exit demo.

**Files:**
- Modify: `web/lib/useImport.ts` (:24–25, :74, :114–115), `web/components/ImportProgress.tsx` (:30), `web/components/ImportSourceCard.tsx` (`Upload.pick` :68–87), `web/e2e/exit-demo.spec.ts` (:425, :478), `web/e2e/README.md`, `docs/requirements.md` (decision log), `docs/review-notes.md` (§11 or a new §12 "M3 Wave 2")
- Create: `web/tests/ImportProgress.test.tsx`
- Test: `web/tests/useImport.test.tsx`, `web/tests/ImportSourceCard.test.tsx`

**Interfaces:**
- `useImport`: `done` without a `thread_id` fails with `NO_THREAD = "The import finished, but Sagaloom did not say which review to open. Find it under Recent imports below."` (distinct from `LOST`). The `409 "turn in progress"` branch is removed (a new import thread cannot be locked; the generic message covers anything else).
- `ImportProgress`: the list is a plain `<ul>` inside a `<div role="status" aria-live="polite">`.
- `Upload`: after each pick the input's value is reset, so the same file can be chosen again after a rejection.
- e2e step 28 reads the provenance line inside `page.getByRole("main")`; step 32 logs `demo step 32: skipped (the sky card was a create)` when `skyEntry` is undefined.

- [ ] **Step 1: Failing tests.** `useImport.test.tsx`: `a dropped stream says the import may still finish` (stream ends without `done` → `LOST`); `done without a thread id says where to look` (`NO_THREAD`, no `push`). `ImportProgress.test.tsx`: `announces progress in a status region` (`getByRole("status")` contains `Found 1 candidate (0 not imported)`; the list has no role); `shows the checking line once checking starts`. `ImportSourceCard.test.tsx`: `an empty file says so` (alert text `That file has no text to import.`); `the same file can be chosen again after a rejection`.
- [ ] **Step 2:** Run them; they fail. Implement.
- [ ] **Step 3: e2e.** Scope step 28's check, add the step-32 log line, rewrap `web/e2e/README.md` to the repo's line style.
- [ ] **Step 4: Docs.** `docs/requirements.md` decision log: one M3 Wave 2 row listing Rulings 1–8 and the answers to the two Open questions, with "Cost if wrong" for each. `docs/review-notes.md`: a short "M3 Wave 2" section (one Show per secret entry, hidden rows unbound, stored-aware secrecy, pill polling rule, proxy errors). README: check every Wave 2 claim against the code (Task 1 already removed the limitation).
- [ ] **Step 5: Exit demo.** Full verification first. Then `cd web && pnpm exec playwright test e2e/exit-demo.spec.ts` once (real calls, allowlisted models only). Copy `test-results/` before any re-run; check ports 8100 and 3100 are free afterwards. Record the time and result in the issue. A failure in a step this wave touched (card Show buttons, delete card copy, step 28/32) is fixed here; an LLM-variance failure gets one re-run, recorded.
- [ ] **Step 6:** Commit with `Refs: #86`, `Closes: #86`, `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

### Task F (#87): Fable wave review, fixes, push

- [ ] Fable reviews M3 Wave 2 as a whole: the diff from the wave's first commit to `HEAD`, read against the design (§4.2, §2, §6–§8), this plan and the M2 Wave 7/8 Fable reviews. Design and pattern adherence first; it confirms every §4.2 item and every source item listed per task is fixed or closed by a written ruling, and that the M2 invariants hold (one secret rule, SSE event set, proxy secret handling).
- [ ] Record the triage in #87 (both repos). Fixes go in #87 with an Opus 5.5 re-review; full verification; the exit demo once more only if a fix touches card markup or a demo step.
- [ ] Push (user delegated 2026-11-09: push after this wave's Fable review fixes land and everything passes; no confirmation needed for this M3 run) `main` to `origin` and `sagaloom`. Update #79–#87 (label `status: done`, ticked criteria, What was done, Commits, Reviews with every finding and its resolution).
- [ ] Copy the ledger and reviews to `internal docs/m3/<YYYY-MM-DD-HHMM>-m3-wave2-*.md`; update `internal docs/handoff.md` (Wave 2 done; what Wave 3 builds on).

---

## Coverage map (design §4.2 and sources → task)

| Item (source) | Task |
|---|---|
| Edit form hidden value in DOM; status select editable (W8 M9); README lines | 1 |
| Card header `entrySecret` vs stored (W8 M8) | 1 |
| Four Show buttons; two "Show secret entry" (W7, #60) | 1 |
| Queue delete line "depend on it" (W8 M10); link-only refs under "mention it" (W8 T5) | 1 |
| `byId` built twice (W4 T3); redundant `byId` term (W8 T5) | 1 |
| Web M12 gaps (W7): masked ref on revealed entry; `getEntries` reset; `read()` stale edge | 1, 4, 4 |
| #60 minors: own prose-flag cite test; loose ≥2 assertion | 1 |
| M14 (W7): heading regex twice; `BLOCK_PARTS`; `argsHoldSecret` strings; Response veil; stale `"true"`; listener sets; regex per render; 3-char aliases | 5, 4, 4, 4, 4, 4, 5, 5 (Q2) |
| Hex one-offs (W7 M8); `--failed` comment (W7 M14) | 5 |
| Proxy `req.text()` and 502 cause (W8 M5); path guard JSON (W8 M4); `PROXY_PREFIX` (W1–2) | 3 |
| Header pill polling (W4 M5, M1 M10) | 6 |
| `setHeld`; parallel-collapse id; `byId`; `norm`/`CHECK_FAILED_TEXT` (W4) | 2 (`byId` in 1) |
| Stale Undo; W3 UI polish | 7 |
| Studio Try it for the reference tool (W1–2) | 7 (Ruling 9) |
| Delete-card dependents on a failed canon load (#60) | Fine (Ruling 10) |
| Import nits (W5 M11, all five) | 8 |
| `useImport`/`ImportProgress` tests; empty-file alert; `From paste:`; step 32 (W5 M10, M13) | 8 |
| W4 test nits (Header settle; keyless-conflict queue test; `ago` already done) | 2 |
| `apiTypes.test.ts` can't go red (W8 M11); generator twice (W8 M13) | 3 |
| `as unknown as LlmResponse` (W3 T3) | 4 |
| Unknown `?thread=` 404 (W3 T4) | 6 |
| Ruling 7 fall-throughs (W1 Settings/Studio nits, `courseNotes`, `["settings"]` prefix; W4 fact rows) | 7, 4, 6, 2 |
| Server-side items found in the same sources (W5 M8 one invalid candidate fails a chunk; W5 T1 bare import-note test) | not this wave: API, for Wave 1 |
