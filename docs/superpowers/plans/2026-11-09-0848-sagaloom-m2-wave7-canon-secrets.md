# Sagaloom M2 Wave 7 (Canon Tab: Entity Chips, Full Entry Page, Hidden Secrets) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Canon tab looks like a product, and the whole app can be screen-shared without showing a secret.
- **Hidden secrets.** One world-level **Show secrets** toggle (header, `sessionStorage`) hides secret entries and secret facts everywhere until it is on. The Under the hood drawer masks secret lines on display, and the record stays verbatim.
- **Server side.** `search_canon` refuses `status="secret"`, and secret entries return no snippet.
- **Full entry page.** Section cards from `##` headings, a Facts panel, "Mentioned in" chips, a source/licence line and an untrusted-source marker.
- **Entity chips.** Type-coloured chips wherever an entry is named, and `@` autocomplete in the composer.
- **Demo world.** Velmar gains one secret entry (user decision 2026-11-09), so the sidebar shows 18 of 19 entries.

**Architecture:**
- **API.**
  - `search_canon` rejects the secret status, and `CanonStore.search` blanks the snippet of secret entries.
  - `export_world` stops revealing how many secret entries exist.
  - A new read-only route lists the entries whose text mentions an entry.
  - The seed gains `ent_0019`, and a script adds missing seed entries to an existing data dir.
  - No graph change, so the Mermaid diagrams stay as they are.
- **Web.**
  - `lib/secrets.ts` holds the per-world toggle, following the `useCourseNotes` pattern (`useSyncExternalStore`).
  - Every component that already hides a secret reads it: a hidden secret is shown when `worldShown || locallyRevealed`.
  - `lib/maskSecrets.ts` masks prompt text for the drawer.
  - `lib/sections.ts` splits an entry body into cards.
  - `lib/mentions.ts` finds entry names in chat text.

**Tech Stack:** API: Python 3.12, FastAPI, pytest. Web: Next.js 16, React 19, TanStack Query, Tailwind v4, Vitest, Playwright. No new dependencies.

**Spec:**
- `docs/superpowers/specs/2026-11-05-0947-sagaloom-m2-design.md`: §2 Wave 7, §3.10 (drawer masking), §3.15 (`SecretsToggle`), §4 (Wave 6 is cut to M3; this wave is next).
- `docs/requirements.md`: R12.10, R12.11 (full), R12.12, R20.1, R20.3, R19.1 (`GET /api/worlds/{id}/entries/{entry_id}/mentions`).
- Deferrals folded in:
  - M1 final review: secret entries expose a body snippet; `search_canon(status="secret")` is allowed; shadcn leftovers and hard-coded hex values; the Studio `try_href` is not URL-encoded.
  - Wave 2 Fable M1: `export_world`'s count reveals the number of secret entries.
  - Wave 4 Fable:
    - M1: the other-world message in `ReviewDetail`;
    - M11: a `LineDiff` of a secret entry shows its title and aliases;
    - M12: `FactList hideAll` for a secret new entry;
    - the "a secret fact: a secret fact → a secret fact" wording.
  - Wave 5 Fable M5: an entry *created* by an import shows no imported-text marker.

**Decisions taken while planning (2026-11-09):**
- Wave 6 (Fan-wiki import) moves to M3 whole (user, spec §4 cut line).
- Velmar gets a 19th entry with status `secret` (user, StoryGuard pattern).

**Issues** (both repos, milestone "M2: bonus tasks and points of difference"):

| Task | Issue | Builder |
|---|---|---|
| Task 0 (this plan, Wave 6 → M3 note) | #52 | — |
| Task 1: server secrets, mentions route, secret seed entry | #53 | Opus |
| Task 2: world Show secrets toggle and view masking | #54 | Sonnet |
| Task 3: drawer masking | #55 | Opus |
| Task 4: full entry page | #56 | Sonnet |
| Task 5: entity chips and `@` autocomplete | #57 | Sonnet |
| Task 6: design tokens, shadcn leftovers, `try_href` encoding (cuttable to Wave 8) | #58 | Sonnet |
| Task 7: demo, docs, evals | #59 | Opus |

The Fable wave-review fixes get #60. Each commit carries `Refs: #N`, and the task's last commit carries `Closes: #N`.

## Global Constraints

- Work goes straight onto `main`. Push to both remotes only after the user confirms.
- **Invariants:**
  - Tools never write.
  - Statuses are per fact.
  - PromptLog records stay verbatim (R20.1): masking happens on display only, client-side.
  - The SSE event set is unchanged.
  - The agent never sees a secret fact, or any fact or body text of a secret entry.
- **The toggle rule (one rule for every component).** A secret is hidden when `secret && !worldShown && !locallyRevealed`.
  - The world toggle is a master switch.
  - Per-item Show buttons stay, and work while the toggle is off.
  - Turning the toggle off does not clear per-item reveals. Navigation remounts components, so they reset anyway.
- **Toggle storage:** `sessionStorage` key `sagaloom.showSecrets.<worldId>`, default off. It is per tab, so a new tab or a different world starts hidden.
- **Secret entry titles.** The agent still sees a secret entry's id, title and type in search hits, so it does not create a duplicate. Chat text naming one is shown as plain text, never as a chip, while hidden. This is a documented limitation.
- **Copy (exact):**
  - Header and drawer toggle: `Show secrets` (an `aria-pressed` button).
  - Drawer mask line: `[secret fact hidden]`.
  - Drawer masked response: `Hidden: this call saw secret facts. Choose Show secrets to read it.`
  - Drawer notice: `Prompts are recorded exactly as sent; secret facts are hidden on screen until you choose Show. Copy as JSON copies the full record.`
  - `search_canon` refusal: `Secret entries can't be searched by status. Search by topic instead.`
  - Masked "Mentioned in" chip: `Secret entry`.
  - No mentions: `No other entries mention it.`
  - Queue summary when both sides and the key are secret: `A secret fact changes`.
  - Other-world review: `This conversation belongs to another world. Switch worlds to review it.`
  - Imported-create marker: `Contains imported text`, with the item `the whole entry`.
  - Untrusted marker: `Untrusted source`.
- A task that changes page or card markup runs the Playwright demo **before** its review. Run evals and Playwright one at a time, in the foreground (memory is tight).

## Review Focus

1. **"Mentioned in" leaking a secret association through a link.** The Mayor's link `secret member of → ent_0004` would list her on the Ashen Choir page. The mentions route counts body and alias text only. `find_mentions` keeps links for the delete check. *(Task 1: `test_mentions_ignore_links`.)*
2. **Drawer lines where `[secret]` is not at the end.** `_fact_line` emits `Key: value [secret] (told by X)`, and Pass 1 lines end `(entry status: …)`. Any line inside an untrusted block that contains `[secret]` or `(entry status: secret)` is masked. The fixture is real `_build_prompt` output, pinned by an API test so it can't drift. *(Task 3: `maskSecrets` fixture tests and `test_judge_prompt_fixture_is_current`.)*
3. **The judge's response restating a secret** with no marker. A call whose request had a masked line shows the masked-response copy in its Response and Raw JSON tabs. Copy as JSON stays verbatim. *(Task 3: `UnderTheHood` test.)*
4. **`@` autocomplete as a secret oracle.** Typing `@Ch` while hidden must not list the secret entry. Neither must chat-text chipping. *(Task 5: `Composer` and `linkEntities` tests.)*
5. **A second tab or a different world.** Each starts hidden. The exit demo toggles in the tab it asserts in. *(Task 2: `secrets.test.ts`, per-world key.)*

---

### Task 1: Server secrets, mentions route, secret seed entry (#53, Opus)

**Files:**
- Modify: `api/sagaloom/store/canon.py`, `api/sagaloom/tools/canon_tools.py`, `api/sagaloom/tools/specs.py` (status description), `api/sagaloom/tools/export.py`, `api/sagaloom/models.py`, `api/sagaloom/web/routes.py`
- Modify: `seed/velmar/entries.json`, `seed/velmar/README.md`; Create: `api/scripts/seed_missing.py`
- Test: `api/tests/store/test_canon.py`, `api/tests/tools/test_canon_tools.py`, `api/tests/tools/test_export_tool.py` (or the existing export tool test), `api/tests/web/test_routes.py`, `api/tests/test_seed.py`

**Interfaces:**
- Produces:
  - `MentionRef(EntryRef)` in `models.py`, adding `status: Status`.
  - `GET /api/worlds/{world_id}/entries/{entry_id}/mentions -> list[MentionRef]`, sorted by id. Returns 404 for an unknown world or entry.
  - `CanonStore.find_mentions(world_id, entry, *, links: bool = True)`. The route passes `links=False`.
  - The seed entry `ent_0019`.

- [ ] **Step 1: Write the failing tests:**
  - `test_search_hit_of_secret_entry_has_empty_snippet`: the snippet is `""` and `facts == []`, and the title and id are still present.
  - `test_search_canon_rejects_secret_status`: the result is an error `ToolMessage` with the exact refusal copy, and no store call is made.
  - `test_export_world_count_excludes_secret_entries`: with and without `exclude_secrets`, `entries` equals the non-secret count. The payload has `"secrets_included": <not exclude_secrets>`.
  - `test_mentions_route_lists_text_mentions`: the Harbour Council page lists entries whose body names it, with `status`.
  - `test_mentions_ignore_links`: on the seed, `ent_0004`'s mentions do not include `ent_0003`. Check first that no body or alias of ent_0003 names the Choir; the Mayor's body doesn't today.
  - `test_mentions_unknown_entry_404`.
  - `test_seed`: 19 entries; `ent_0019` has status `secret`.
  - `test_seed_missing_adds_only_absent_entries`: an edited `ent_0001` is untouched, and a deleted `ent_0019` is restored.
- [ ] **Step 2: Run** `cd api && uv run pytest -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Add the seed entry `ent_0019`**, consistent with the other 18 by construction:
  - title `The Choir Ledger`, type `item`, status `secret`;
  - body: a cipher ledger kept in Ilsa Corran's crypt below the Tidehall, listing every singer of the Ashen Choir, the Mayor among them (name her as `Mayor Elsbeth Varr`, so her page shows a masked "Mentioned in" chip);
  - facts: `Kept in: Ilsa Corran's crypt below the Tidehall`, `Lists: Every member of the Ashen Choir`, `Written in: A cipher of moon phases`;
  - no links.

  Update the seed README (19 entries, the secret entry). `scripts/seed_missing.py` upserts only the seed ids absent from the `velmar` world. Use the same `Settings()` and store construction as app startup, and never read `.env` yourself.
- [ ] **Step 4: Implement** the snippet, the refusal (checked before the store call), the export count, `MentionRef`, `links=` and the route. Then update the `search_canon` status description in `specs.py`: canon, myth or rumour, not secret.
- [ ] **Step 5: Run** `cd api && uv run pytest -q`. Expected: all pass. Grep the unit tests for hard-coded `18`, and fix any that the seed change breaks.
- [ ] **Step 6: Commit** with `Refs: #53` (`feat: secret entries hidden from search, mentions route, secret seed entry`).

---

### Task 2: World Show secrets toggle and view masking (#54, Sonnet)

**Files:**
- Create: `web/lib/secrets.ts`, `web/components/SecretsToggle.tsx`
- Modify: `web/components/Header.tsx`, `CanonList.tsx`, `EntryView.tsx`, `FactList.tsx`, `FactTable.tsx` (`SecretValue`, `Cite`), `DiffView.tsx` (`BodyDiff`, `LineDiff`), `ApprovalCard.tsx`, `ReviewDetail.tsx`, `web/lib/review.ts`
- Test: create `web/tests/secrets.test.ts`, `SecretsToggle.test.tsx`; modify `CanonList`, `EntryView`, `FactList`, `DiffView`, `ApprovalCard`, `review`, `ReviewDetail` and `Header` tests

**Interfaces:**
- Produces:
  - `useShowSecrets(worldId: string | undefined): [boolean, (on: boolean) => void]`. It is always false without a world id.
  - `SHOW_SECRETS_KEY = (worldId: string) => \`sagaloom.showSecrets.${worldId}\``.
  - `<SecretsToggle />` reads the world from `useWorld`.
  - `FactList` gains `hideAll?: boolean`.
  - `LineDiff` gains `secret?: boolean`.

- [ ] **Step 1: Write the failing tests:**
  - `secrets`:
    - default false;
    - set true persists under the per-world key;
    - another world id reads false;
    - two hook users stay in sync;
    - a throwing `sessionStorage` falls back to memory.
  - `SecretsToggle`: `aria-pressed` follows the state.
  - `CanonList`: with Velmar-like data (one secret entry), it lists 18 links; with the toggle on, 19. The sidebar button uses the same state.
  - `EntryView`: a secret entry is shown when the toggle is on; a secret fact is shown when the toggle is on. The per-item Show still works when it's off.
  - `FactList`:
    - `hideAll` hides canon-status facts too (key `Secret fact`);
    - the toggle reveals everything, `hideAll` facts included.
  - `SecretValue`, `Cite`, `BodyDiff`: revealed when the toggle is on.
  - `LineDiff` with `secret`: title and alias values are masked behind one Show.
  - `ApprovalCard`: for a create with `after.status === "secret"`, "Facts to commit" hides every fact (W4 M12), and an update's `LineDiff` of a secret entry is masked (M11).
  - `proposalSummary`: when the key, the existing side and the proposed side are all masked, it returns `A secret fact changes`.
  - `ReviewDetail`: a thread whose proposals carry another `world_id` shows the other-world copy.
- [ ] **Step 2: Run** `cd web && pnpm vitest run`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - Copy `useCourseNotes`'s external-store shape. Notify listeners per key, and keep a `Map` fallback for when storage is unavailable.
  - Put the toggle in the Header before `CourseNotesToggle`.
  - Each listed component ORs the hook into its existing hidden test (the toggle rule).
  - `CanonList` drops its local `showSecrets`.
  - The card passes `hideAll` for a secret create and `secret` to `LineDiff` when `before` or `after` is secret.
- [ ] **Step 4: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build` (lint takes more than 2 minutes, so give it a long timeout), then the Playwright demo. Afterwards, check that ports 8100 and 3100 are free. Expected: all pass. Demo steps that read the sidebar or the Mayor's facts may need the new count; fix them in this task.
- [ ] **Step 5: Commit** with `Refs: #54` (`feat: world-level Show secrets toggle across views`).

---

### Task 3: Drawer masking (#55, Opus)

**Files:**
- Create: `web/lib/maskSecrets.ts`, `web/tests/maskSecrets.test.ts`, `web/tests/fixtures/judge-prompt.txt`, `api/tests/check/test_prompt_fixture.py`
- Modify: `web/components/UnderTheHood.tsx`, `web/tests/UnderTheHood.test.tsx`

**Interfaces:**
- Consumes: `useShowSecrets` (Task 2).
- Produces: `maskPrompt(text: string): { text: string; masked: number }`.

**Rulings** (record them in the ledger as `Ruling: what — why — cost if wrong`):
- **Masking rule, inside `<untrusted_data …>` blocks only.**
  - A line containing `[secret]` or `(entry status: secret)` becomes `[secret fact hidden]`.
  - In a block with a line `Entry status: secret`, every line after that line becomes `[secret fact hidden]`. Title, Type and Entry status stay.
  - Text outside the blocks is never masked.
  - Cost if wrong: a secret in an unmarked format shows. The fixture test guards the format.
- **Response and Raw JSON.** A call whose request masked at least one line shows the masked-response copy in both tabs while hidden, because the judge's output has no markers. Cost if wrong: an extra click on Show secrets.
- **Copy as JSON** (per call and per turn) stays verbatim. The clipboard is not the screen, and R20.3's Copy is for the record.
- The drawer's own `Show secrets` button drives the same world hook, not a separate state.

- [ ] **Step 1: Generate the fixture.** Write `api/tests/check/test_prompt_fixture.py`. It builds `_build_prompt` for an update of `ent_0003` (`Age: 60`), with related `[ent_0002, ent_0003, ent_0019]` from the seed, and asserts the result equals `web/tests/fixtures/judge-prompt.txt`. On the first run, write the file from the test's output, then commit it. Add a header comment to the test explaining how to regenerate it.
- [ ] **Step 2: Write the failing web tests:**
  - `maskPrompt(fixture)`:
    - the output contains neither `Yes, at every full Ister` nor `Sings with the Ashen Choir`;
    - the body and facts of `ent_0019` are gone, and its `Title:` line stays;
    - non-secret lines (`Age: 54 [canon]`) are unchanged;
    - `masked > 0`.
  - A line `Key: v [secret] (told by Ilsa)` is masked.
  - A Pass 1 line `Existing: … (entry status: secret)` is masked.
  - `[secret]` outside any block is not masked.
  - `UnderTheHood`:
    - the Request tab shows `[secret fact hidden]`;
    - Response and Raw JSON show the masked-response copy;
    - after the drawer's `Show secrets`, all three are verbatim;
    - Copy as JSON writes the verbatim record either way;
    - the notice copy is exact;
    - a call with no secrets shows its response unmasked.
- [ ] **Step 3: Run** `cd web && pnpm vitest run` and `cd api && uv run pytest -q tests/check/test_prompt_fixture.py`. Expected: the web tests FAIL and the API test PASSES.
- [ ] **Step 4: Implement** `maskPrompt` and the drawer changes. `Content` renders the masked text. The masked untrusted blocks keep their `data-testid="untrusted"` styling.
- [ ] **Step 5: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build`, then the Playwright demo (the step 7 drawer assertions must still hold). Expected: all pass.
- [ ] **Step 6: Commit** with `Refs: #55` (`feat: Under the hood masks secrets on display`).

---

### Task 4: Full entry page (#56, Sonnet)

**Files:**
- Create: `web/lib/sections.ts`, `web/tests/sections.test.ts`
- Modify: `web/components/EntryView.tsx`, `web/lib/api.ts` (`getMentions`), `web/lib/types.ts` (`MentionRef`), `web/tests/EntryView.test.tsx`

**Interfaces:**
- Consumes:
  - `GET …/mentions` (Task 1);
  - `useShowSecrets` (Task 2);
  - `importedSections` (`lib/imported.ts`).
- Produces:
  - `sectionsOf(body: string): { heading: string; text: string; imported: boolean }[]`.
  - `getMentions(worldId, entryId): Promise<MentionRef[]>`, with query key `["mentions", worldId, entryId]`.

- [ ] **Step 1: Write the failing tests:**
  - `sectionsOf`:
    - no headings gives one `Description` card;
    - text before the first `## ` is `Description`;
    - an empty body gives `[{heading: "Description", text: "", imported: false}]`;
    - `## Imported from notes.md (2026-11-07)` gives `imported: true`;
    - `### ` is not a split point.
  - `EntryView`:
    - one card per section; an empty Description shows `No description yet.`;
    - "Mentioned in" renders chips linking to `/canon/<id>`;
    - a secret-status mention shows `Secret entry` (no title, no link) until the toggle is on;
    - none gives `No other entries mention it.`;
    - the provenance line:
      - `Source: your notes` for `user`;
      - `Source: Wikipedia reference · <url>` for `reference`;
      - `Source: official canon · <url> · Licence <licence>` for `official`;
      - the url opens in a new tab with `rel="noreferrer"`;
    - `Untrusted source` for `trusted: false`;
    - an untrusted `user` entry with no import headings shows `Contains imported text` with `the whole entry` (W5 M5);
    - the version and edited line stay.
- [ ] **Step 2: Run** `cd web && pnpm vitest run`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - Section cards reuse the current `CARD` style. An imported card's heading reads `Imported from …` with the marker colour.
  - "Mentioned in" goes in the Facts aside, under the facts.
  - A secret entry that is still hidden keeps today's hidden card, and its mentions are not fetched.
- [ ] **Step 4: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build`, then the Playwright demo. Expected: all pass.
- [ ] **Step 5: Commit** with `Refs: #56` (`feat: full entry page with sections, mentions and provenance`).

---

### Task 5: Entity chips and `@` autocomplete (#57, Sonnet)

**Files:**
- Create: `web/lib/mentions.ts`, `web/tests/mentions.test.ts`, `web/tests/Composer.test.tsx`
- Modify: `web/components/ChatThread.tsx`, `Composer.tsx`, `CanonList.tsx`, `FactList.tsx`, `web/tests/CanonList.test.tsx`, `FactList.test.tsx`, `ChatPage.test.tsx`

**Interfaces:**
- Consumes: `EntityChip`, `useShowSecrets`.
- Produces:
  - `type Named = Pick<Entry, "id" | "title" | "type" | "aliases" | "status">`.
  - `linkEntities(text: string, entries: Named[], showSecrets: boolean): (string | { entry: Named; text: string })[]`.
  - `suggestEntries(query: string, entries: Named[], showSecrets: boolean, limit = 8): Named[]`.
  - `Composer` gains `entries?: Named[]` and `showSecrets?: boolean`.
  - `FactList` gains `entries?: Named[]`, used for `refs` and `told_by` chips.

**Matching rule:**
- Match `ent_\d{4}` ids present in `entries`, plus titles and aliases of 3 or more characters.
- Matching is case-insensitive and on word boundaries.
- The longest match wins at each position: "The City of Velmar" is one chip, not "Velmar".
- Secret-status entries never match while hidden.
- Chips link to `/canon/<id>` and keep the matched text as the chip name.

- [ ] **Step 1: Write the failing tests:**
  - `linkEntities`:
    - an id, a title and an alias each become a chip;
    - the longest match wins;
    - there is no match inside a word (`Velmarish`);
    - a secret entry stays text while hidden and becomes a chip when shown;
    - an unknown `ent_9999` stays text.
  - `suggestEntries`:
    - prefix matches rank before substring matches;
    - aliases match;
    - secrets are excluded while hidden;
    - the limit is 8.
  - `Composer`:
    - `@el` opens a `listbox` with `Mayor Elsbeth Varr`;
    - ArrowDown then Enter inserts `Mayor Elsbeth Varr ` in place of `@el` and does **not** send;
    - Escape closes it;
    - `@` inside a word (`me@x`) does not open it;
    - the textarea has `role="combobox"`, `aria-expanded` and `aria-activedescendant`;
    - the sent message is plain text.
  - `ChatPage`: the assistant text `Ister, the red moon (ent_0012)` renders chips.
  - `CanonList`: each row has a type dot.
  - `FactList`: `told_by` matching an entry renders a chip, and `refs` render chips.
- [ ] **Step 2: Run** `cd web && pnpm vitest run`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** `ChatThread` passes the world's entries (it already loads `canon`) and the hook value to the text renderer and the Composer. Only assistant text is chipped; author messages stay as typed.
- [ ] **Step 4: Run** `cd web && pnpm vitest run && pnpm lint && pnpm build`, then the Playwright demo. Expected: all pass. Demo selectors that read assistant text by `getByText` may now span chips; switch them to `toContainText` on the message.
- [ ] **Step 5: Commit** with `Refs: #57` (`feat: entity chips in chat, sidebar and facts; @ autocomplete`).

---

### Task 6: Design tokens, shadcn leftovers, `try_href` encoding (#58, Sonnet; cuttable to Wave 8)

**Files:**
- Modify: `web/app/globals.css`, every component with a hard-coded `#rrggbb` (18 files today: `grep -rlE "#[0-9a-fA-F]{6}" web/components web/app`), `api/sagaloom/studio.py`
- Delete: unused `web/components/ui/*` and their dependencies, if `grep` shows no import of them
- Test: `api/tests/test_studio.py` (or the existing Studio test)

- [ ] **Step 1: Write the failing test:** `try_href` for each card is URL-encoded (`prompt=What%20do%20we%20know…`, decoded back to the original), using `urllib.parse.quote`.
- [ ] **Step 2: Implement the encoding.** Then add each repeated hex as a named token under `:root` and `@theme inline`, in the existing `--color-*` style (for example, `--color-prose: #e3dfd5` and `--color-prose-muted: #c9c6bd`), and replace the literals. Leave a one-off value in place only if naming it would be noise, and list those in the report. Remove the unused shadcn components and dependencies, and the stale `--accent`/`destructive`/dark-variant leftovers in `globals.css`. Keep everything a component imports.
- [ ] **Step 3: Run** `cd api && uv run pytest -q`, then `cd web && pnpm vitest run && pnpm lint && pnpm build`, then the Playwright demo. Expected: all pass. Take one screenshot of Canon, Chat with a card, and the drawer, and compare it by eye with the current `main` build. Report any visible change.
- [ ] **Step 4: Commit** with `Refs: #58` (`chore: colour tokens, shadcn leftovers, encoded Try it links`).

---

### Task 7: Demo, docs, evals (#59, Opus)

**Files:**
- Modify: `web/e2e/exit-demo.spec.ts`, `web/e2e/README.md`, `README.md`, `docs/review-notes.md`, `docs/requirements.md` (decision log; R12.10–R12.12 done-when ticks), `docs/superpowers/specs/2026-11-05-0947-sagaloom-m2-design.md` (§5: Wave 6 cut to M3, the secret seed entry)

- [ ] **Step 1: Extend the demo** with a Wave 7 step, all in the main page (`sessionStorage` is per tab):
  1. On `/canon`, the Entries nav lists 18 entry links and no `The Choir Ledger`. Click the header `Show secrets`: 19 links. Click it again.
  2. On `/canon/ent_0003`, the secret fact is masked. "Mentioned in" holds a `Secret entry` chip.
  3. In Chat, send `Mayor Elsbeth Varr is sixty years old.` and wait for the card. If the agent asks a question instead, throw with its reply (the Wave 4 pattern). Open the drawer and pick the judge call whose request contains `[secret fact hidden]`. The request does not contain `Yes, at every full Ister`. Click the drawer's `Show secrets`: it does. Click it again, then reject the card.
  4. Type `@Ister` in the composer, pick the option, and check that the box holds `Ister, the red moon`. Clear the box.
- [ ] **Step 2: Run the Playwright demo twice in a row, one run at a time.** Expected: PASS both times. Copy `test-results/` before re-running a failed run.
- [ ] **Step 3: Run the evals once** (`cd api && uv run pytest -m eval -v -s`, about 9 minutes, foreground, nothing else running), because the seed changed. Expected: every eval at its target. Record the scores. The canary eval's known ~3% flake is a Wave 8 item; re-run it alone if it trips.
- [ ] **Step 4: Update the docs:**
  - README:
    - walkthrough 12, "Share your screen safely" (the toggle, the drawer, `@`, the entry page);
    - "19 entries";
    - limitations:
      - masking is client-side and per tab;
      - Copy as JSON is verbatim;
      - the agent sees secret entries' titles but never their text.
  - `docs/review-notes.md`: a section on hidden secrets (what is masked where, and why the records stay verbatim).
  - Requirements decision log: this wave's rulings, the cut of Wave 6 to M3, and the secret seed entry.
- [ ] **Step 5: Commit** with `Closes: #59` (`docs: Wave 7 demo, walkthrough, review notes`).
