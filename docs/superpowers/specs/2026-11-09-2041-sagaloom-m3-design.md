# Sagaloom M3 design: clean-up, then fan-wiki import

_Written 2026-11-09 after M2 closed (`2eb86ea`). Source of truth for requirements stays `docs/requirements.md`; this document says what M3 builds, in what order, and which calls are already made. Earlier designs: M1 `2026-11-04-sagaloom-design.md`, M2 `2026-11-05-0947-sagaloom-m2-design.md` (its §2 Wave 6, §3.2, §3.11, §3.12 and F1 still apply unless amended here)._

---

## 1. Intent

M2 left two things behind on purpose:

1. **A backlog of about 50 deferred minors** from every M2 wave, each ruled "M3" by a review (smells, robustness edges, test gaps, UI nits, two documented README limitations). The user wants **the whole list** cleared, not a subset: M3 should leave no known debt behind.
2. **Fan-wiki import** (old M2 Wave 6, R11.6), cut from M2 whole. It is the one import feature no competitor has (Realmweaver, LitMemo and StoryGuard import only the author's own text), and it completes Hard 5 / Medium 3 with a second external data source.

**Order (user decision):** clean-up first, then wiki import. Several minors sit in the import pipeline that wiki import reuses (`aclosing` on `_extraction`, `usage` on total extraction failure, synchronous Chroma lookups, untested `useImport`), so the wiki wave builds on clean code.

## 2. Goals, non-goals, anti-goals

**Goals**
- Every item in §4's inventory is fixed, or closed by a written ruling (fix, fine, or "documented limitation stays") recorded in its issue's Reviews section. Nothing stays "M3".
- Fan-wiki import works from the Import page and from chat, with the real licence read and shown, attribution in exports, and every page reaching canon only through `check` and the approval gate.
- All M2 invariants (Fable whole-M2 review §4) still hold at the end of every wave.

**Non-goals**
- The spec §4 "Stay in M3" features (duplicate merge, Obsidian vault import, whole-world scan, divergent-world mode, continuity per world R11.6.8, JSON export, timeline fields, Ctrl+K, help panel, cost by step, LLM critique). They stay in the backlog for a later milestone.
- Category imports and whole-wiki imports (see §5.1).
- Course-review preparation. The user will say when (handoff §3 rule 9).

**Anti-goals (a failure even if it works)**
- Fandom text committed to the repo (F1, K1).
- A faked browser User-Agent, HTML scraping, or any retry around a 402/403 block (R11.6.9).
- A clean-up that changes user-visible behaviour beyond what its item names, or that weakens an invariant (secrets, provenance, verbatim records, guard fails closed, tools never write).
- A change to the SSE event set (`token, tool_call, tool_result, node, llm_request, llm_response, interrupt, usage, done, error`).

## 3. Shape: three waves

| Wave | Theme | Size |
|---|---|---|
| **M3 Wave 1** | Server and import-pipeline clean-up (API code and its tests) | L |
| **M3 Wave 2** | Web clean-up: secrets UI, proxy, Review/queue, smells, UI nits (web code and its tests) | L |
| **M3 Wave 3** | Fan-wiki import (R11.6, R11.5.5, R11.4.8) | L |

Tests travel with the code they cover (a server test gap goes in Wave 1, a web one in Wave 2). Tooling items go to whichever side they touch. **Builder's call:** the exact task split inside each wave, keeping one issue per task.

M3 waves are named "M3 Wave N" everywhere (issues, ledgers, files) so they don't collide with M2's wave numbers.

## 4. Clean-up inventory

Each line names the item; the full finding (file, line, reason) is in the cited review. The plan writer must open those sources, not work from these one-liners. Sources:

- Wave 8: `internal docs/m2/2026-11-09-2020-wave8-fable-review.md` §2 (M4–M13) and §6.1; the "Carried to M3" list at the end of `docs/superpowers/plans/2026-11-09-1527-*-wave8-hardening.md`.
- Wave 7: `internal docs/m2/2026-11-09-1348-wave7-*.md` (M8, M11, M12, M14 and the Show-button items).
- Wave 5: `internal docs/m2/2026-11-07-1145-wave5-*.md`.
- Wave 4: `internal docs/m2/2026-11-06-1354-wave4-*.md`.
- Wave 3: `internal docs/m2/2026-11-06-0842-wave3-*.md`.
- Waves 1–2: `internal docs/m2/2026-11-05-1155-wave1-*.md`, `2026-11-05-1649-wave2-*.md`.

If a source lists an M3 item that is missing below, it is in scope anyway. Add it to the matching wave.

### 4.1 M3 Wave 1: server and import pipeline

*Robustness*
- `_extraction` without `aclosing` (W5).
- No `usage` event on a total extraction failure (W5).
- Synchronous Chroma lookups per candidate in extraction (W5). Run them off the event loop or batch them.
- `PRAGMA table_info` on every registry connect (W5). Do it once.
- `sse_response` `on_close` tidy-up (W5).
- U+2028 / U+2029 / U+0085 accepted by the import filename pattern (W5).
- Memory lock map is never pruned. Move it to `AppDeps` and prune it the way `AppDeps.locks` is pruned (W3).
- Partial store failure reporting in memory, and `MemoryResult.reason` (W3).
- `GET /threads` does one `aget_state` per thread. Together with the header pill reading every checkpoint every 15 s, this is the cost to cut: a cheaper listing on the server (for example, counts kept on the registry row), and the client half in Wave 2 (M1 M10, W4).
- `list_by_role` full scan (W1–2).
- XFF trust and rate-limiter memory (W1–2, README limitations). **Builder's call:** fix within the current single-process design (for example, bounded limiter memory). If the fix needs a product decision (a trusted-proxy setting), raise it with the user rather than choosing.

*Version and commit*
- `Entry.version` gets `ge=1`, then regenerate the types (Wave 8 M7).
- A create that loses the id race says "an entry with that id already exists", not "(v0 → v1)" (Wave 8 M6).
- The "entry changed since it was checked" string is written twice in `nodes.py`. Fold it to one writer (Wave 8 T2).
- The world-mismatch refusal copy in `commit` is misleading (Wave 8 T3).
- Add a node-vs-real-store version-conflict test (Wave 8 T2).

*Structure and smells*
- A shared structured-classify retry helper for guard and router (W3), the private guard retry constants, and the guard log "unknown" (W1–2).
- Repeated settings warning; `routes` importing `TOOL_SPECS` (W1–2).
- `_first_line` duplicated; private `_drain` / `_ev` imports (W5).
- `GEMINI_MODEL` location; typing `_ask_judge`; `exc.request` in the Gemini mapping (W3). Gemini is still never called: tests use fakes.
- Pydantic serializer warnings (W3); pytest-asyncio loop-scope warning (W1–2, W8).
- `seed_missing` rule (b) prints nothing (W7 M11).
- Empty-lookup taint note (W1–2); the Mermaid `tools` label (W1–2). If the label changes, regenerate both diagrams; `test_diagram.py` pins them.
- `find_mentions(links=True)` default has no production caller (W8 T5).

*Tests*
- Test HTTP clients (W3); the `_error_event` 503 test (W3); the API-side M12 test gaps (W7).

### 4.2 M3 Wave 2: web

*Secrets UI (the two README limitations go away)*
- The Edit form's hidden fact value is bound as `type="password"`, so it sits in the DOM. A hidden row must not carry the value until Show (W8 M9).
- The fact status select stays editable on a hidden row (W8 M9). Remove both lines from the README limitations once fixed.
- The card header uses `entrySecret`; it should use the stored entry (`storedSecret`), like Edit (W8 M8).
- A secret create card shows four Show buttons, and there are two "Show secret entry" buttons. Collapse them (W7).
- The queue's delete line says "N entries mention it" for link-only dependents too; make it "depend on it" (W8 M10).
- M14 smells: dated-heading regex written twice, `BLOCK_PARTS`, `argsHoldSecret` string args, the Response tab relying on the veil, the stale `"true"` in `secrets.tsx`, listener sets, a regex built per render, 3-character aliases (W7).
- Five hex one-offs; replace them with tokens (W7 M8).

*Proxy*
- `req.text()` moves before the `try`; the 502 handler logs its cause (W8 M5).
- The path guard answers JSON like the other errors (W8 M4).
- `PROXY_PREFIX` duplication (W1–2).

*Review, chat, Studio*
- The header pill polls every checkpoint every 15 s. Use the Wave 1 listing, and poll less or only while something runs (W4).
- `setHeld` during render; the parallel-collapse `ToolMessage` id; `byId` built twice; `norm` and `CHECK_FAILED_TEXT` move into `lib` (W4).
- Stale Undo copy; W3 UI polish items.
- Studio "Try it" for the reference tool (W1–2).
- Import nits: `done` without `thread_id` copy, `role="status"` on a list, "Found 1 candidate" (W5).

*Tests and tooling*
- `useImport` stream drop and `ImportProgress` tests; the page-wide `From paste:` e2e check (W5).
- W4 test nits; web-side M12 test gaps (W7).
- `apiTypes.test.ts` can't go red under vitest. Add a typecheck step that does (W8 M11).
- The generator command is written twice (W8 M13).

### 4.3 Items already ruled Fine

Items the Wave 8 Fable review ruled **Fine** (§6.1, M12, M14, M15) stay closed. They are not reopened.

## 5. M3 Wave 3: fan-wiki import

The M2 spec's Wave 6 (§2), §3.2, §3.11, §3.12 and F1 apply, with these user decisions and amendments.

### 5.1 How the author picks pages (user decision: paste URLs)

- The Import page's **Fan wiki** card (replacing "Coming soon") has one textarea: paste page URLs, one per line. Primary action: "Extract entries".
- **1–10 URLs per import** *(my call; R11.6.1 allowed 25 for categories, which are dropped)*. One host per import *(my call: one licence per import keeps the Review header and the NC warning simple)*. The UI validates host, URL shape, count and duplicates before sending.
- **Accepted URLs:**
  - `https://<sub>.wikipedia.org/wiki/<Title>`, `https://<sub>.fandom.com/wiki/<Title>` and `https://<sub>.fandom.com/<lang>/wiki/<Title>`.
  - Host matching is suffix-with-dot (so `evilwikipedia.org` is rejected); https only.
  - The query and fragment are dropped, and the title is percent-decoded.
  - Anything else is refused with a clear message.
- **No category imports.** This amends R11.6.1 (inputs become `urls`) and R11.6.3 (selective-only is now met by the URL cap). Update `docs/requirements.md` and its decision log in the wave's first task.

### 5.2 Chat tool (user decision: both page and chat)

- An optional `import_wiki` agent tool with one arg, `urls` (1–10, same rules). It is listed in `tools/specs.py` and can be switched off in Studio like the other optional tools (R11.G1, R11.G3).
- It returns a `Command` that adds proposals, like `create_or_update_entry`. **The agent never sees page text.** Its tool result carries counts, titles and not-imported reasons only.
- **Builder's call:** the wording of that result.
- The Import page (`POST /api/worlds/{id}/imports` with `kind: "wiki"`) and the tool share one core, `importing/wiki.py`. Both reach `commit` only via `check` and `approval_gate`, and the existing structure tests must cover the new path.

### 5.3 Fetching (R11.6.2, R11.6.9, R11.6.10, R11.6.12, R11.4.8)

- **One shared client.** `wiki/client.py` is extended (it already serves `real_world_reference`), with one shared `httpx` client and these rules:
  - honest User-Agent `Sagaloom/<version> (+repo URL)`;
  - about 1 request per second per host;
  - on-disk cache under `data/cache/wiki`;
  - no retry on 402/403.
- **Calls:**
  - Pages are read through `action=parse` (wikitext and categories, with `redirects` on). HTML is never scraped.
  - The licence comes from `action=query&meta=siteinfo&siprop=rightsinfo` and is stored exactly as reported. If it can't be read, the whole import stops with an explanation (R11.6.12).
- **Redirects.** HTTP 3xx redirects are followed only while every hop stays on an allowed host. The final URL becomes the `source_url`.
- **Errors.** One page failing does not fail the import. A 402, 403, 429 or 404 page goes to the existing "Not imported" list with its reason and a "paste the text instead" link to the Paste card (R11.6.10).

### 5.4 Clean-up and extraction (R11.6.4, R13.6)

- Wikitext is stripped before extraction: templates, navboxes, references, tables, files and images (text only). The infobox's parameters may seed the type and facts.
- **Builder's call:** whether to use a wikitext parser library (such as `mwparserfromhell`) or a hand-written stripper. Either needs tests on real cached pages.
- Then the **same injection-safe extractor** runs: a structured-output call with no tools bound, text wrapped `import:wiki:<host>/<title>`. **The stored text is a verbatim slice of the stripped text** (`locate`). The 4,000-character body cap applies, with `(truncated on import)`.
- **One proposal per page** (R11.6.5). A title or alias match is a merge update, as in Wave 5 (`## Imported from <url> (<date>)`, facts unioned).

### 5.5 Provenance, licence, attribution (R11.6.7, R11.6.13, R11.5.5)

- **A list of sources per entry (user decision, 2026-11-09).**
  - R2.S gains `sources`: a list of `{kind: official | reference, url, licence, licence_url, nc, added_at}`.
  - `licence` and `licence_url` hold the MediaWiki `rightsinfo` `text` and `url` exactly as reported (*my call*). `nc` is computed once, at fetch time, from either one.
  - A merge **appends** a source and never replaces one, so no source and no NC flag is ever lost. The same URL is not added twice.
  - The existing `source`, `source_url` and `licence` fields stay as the entry's primary provenance: the highest-precedence kind (official > reference > user), and within that kind the first source added (*my call*). `trusted` is unchanged: an untrusted entry never becomes trusted again.
  - **Existing stored entries:** an entry without `sources` that has a `source_url` reads as a one-item list from its current fields. **Builder's call:** whether that happens lazily or through a migration.
  - Update the R2.S table in `docs/requirements.md` and regenerate the types.
- **The reference tool records licences too (user decision).** `real_world_reference` reads the Wikipedia host's `rightsinfo` through the same shared client (cached; one call per host) and records a `reference` source with that licence. If the licence can't be read, the reference still works, and its source says "licence not reported". A licence is never assumed.
- New wiki entries are `source=official` with one `official` source and `trusted=false`.
- **NC detection:** the licence text or URL says non-commercial (`NC`, `NonCommercial`, `-nc`). An entry is NC when any of its sources is. NC shows as an amber warning box above the Review queue, and as an NC label on the entry page, the sidebar and the export.
- **Licence display:** the Review detail header shows "Licence: <text as reported>". The demo and e2e strings use whatever en.wikipedia.org actually reports (*my call*). If that isn't "CC BY-SA 4.0", the M2 spec's demo line changes to match.
- **Exports:** an export that includes any entry with sources adds an `ATTRIBUTION.md` (R11.5.5, extended to references). It lists every source URL with its licence (or "licence not reported"), gives the share-alike notice and flags NC content. "Leave out secrets" still applies first.

### 5.6 Demo, tests, evals

- **Demo cache (R11.6.11, F1):** pre-cached **Wikipedia** pages (Rivendell, Gandalf, Shire (Middle-earth)), committed as fixtures with their CC BY-SA 4.0 attribution. No Fandom text is committed.
- **Exit demo:** a new step pastes the three URLs on the Fan wiki card. Review shows 3 official entries with "Licence: CC BY-SA 4.0"; approve, then export contains `ATTRIBUTION.md`. The e2e data dir needs the cache seeded. **Builder's call:** how.
- **Unit tests:** no network; HTTP is faked. Cover the host allowlist (including look-alike hosts), redirect hops off the allowlist, each error code with no 402/403 retry, an unreadable licence stopping the import, NC detection and labels, merge precedence, attribution contents, and the structure test for the tool path.
- **Opt-in live test** (`-m live`): one real `en.wikipedia.org` page.
- **Canary (R13.8):** extend the canary eval with a cached wiki-shaped fixture page that holds a hidden instruction. Target 10/10, as for paste.
- **Docs:**
  - README walkthrough, bonus table and limitations (K1 stays stated).
  - Review notes.
  - Requirements Done cells and decision log.
  - If the graph changes, regenerate both Mermaid diagrams.

## 6. Constraints carried from M2

- All LLM calls go to OpenRouter, using only models in `api/sagaloom/allowed_models.json`. Gemini is never called. `.env` / `.env.local` are never read or printed.
- The secret rule stays one rule: hidden when `secret && !worldShown && !locallyRevealed`, following the content's world.
- Regenerate the generated API types after any API model change (`pnpm types:gen`). `pnpm types:check` runs in every verification step, along with `uv run pytest -q`, `pnpm vitest run`, `pnpm lint` and `pnpm build`.
- Run the API as a single process (the commit guarantee).
- `langchain-openai` stays pinned `<1.8`.

## 7. Process (unchanged from M2)

- **Setup:** a milestone "M3" in both repos. Each wave gets a plan (`superpowers:writing-plans`), approved by the user, then issues in both repos in the same order (next number **#69**). Issue bodies use Aim / What was done / Success criteria / Status / Reviews / Requirements / Commits.
- **Builds:** SDD with Sonnet 5.5 builders for straightforward tasks and Opus 5.5 for hard or security-sensitive ones (all of Wave 3's fetching, URL validation and provenance work). Every task review and re-review is Opus 5.5, then a Fable review per wave and a Fable whole-M3 review at the end. Reviewers check design and pattern adherence first. Every review finding and its resolution goes in the issue's Reviews section.
- **Commits and pushes:** commits go straight to `main` with `Refs:` / `Closes:` trailers. Confirm with the user before every push, then push to both remotes.
- **Records:** wave records go to `internal docs/m3/YYYY-MM-DD-HHMM-m3-waveN-*.md`.

## 8. Left to the builder

- The task split inside each wave and the order of the clean-up items.
- The exact form of the cheaper thread listing (§4.1) and the pill's new polling rule (§4.2), within "no visible change except it is cheaper".
- The wikitext stripping approach, and how the e2e data dir gets the wiki cache.
- The copy for the tool result, the error messages and the NC warning, written in the app's existing plain style.
- For any §4 item whose fix turns out to need a product decision, raise it with the user (one question, with options) rather than choosing.
