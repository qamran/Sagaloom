# Exit demo (Playwright)

`exit-demo.spec.ts` walks the whole product end to end: M1 (ask, conflict, Save as myth, Under the hood),
Wave 1 (input guard), Wave 2 (reference tool, Markdown export, tool toggles) and Wave 3 (long-term memory,
the router mode chip, the highlighted agent graph), Wave 4 (the Review tab: a two-proposal batch, the
complete fact table, one submit), Wave 5 (the Import page: paste notes, review the extracted proposals, the
imported-text marker), Wave 7 (hidden secrets, the entry page, the drawer mask, `@` suggestions), Wave 8 (the delete
card's linked-entry count) and M3 Wave 3 (fan-wiki import into its own world, step 35).

Run it from `web/`:

    pnpm exec playwright test

It starts its own API (port 8100) and web app (port 3100) on a throwaway data folder, so it never touches
your dev servers or `data/`. The web app builds into `web/.next-e2e/` (`NEXT_DIST_DIR`, read by `next.config.ts`):
Next 16 lets only one `next dev` use `.next/dev`, so the demo can run while your `pnpm dev` is up. `tsconfig.json`
excludes `.next-e2e`, so a normal `tsc` or `pnpm build` never checks its generated types. Each run points the
git-ignored `web/next-env.d.ts` at `.next-e2e`; the next normal `pnpm dev` or `pnpm build` points it back. Before uvicorn starts, the API command runs `uv run python scripts/seed_wiki_cache.py
"<data dir>"`, which copies the committed Wikipedia fixtures (`api/tests/fixtures/wiki/`: Rivendell, Gandalf, The
Shire and the `en.wikipedia.org` licence) into `<data dir>/cache/wiki/` (R-W3-10), so the fan-wiki step is served
from the cache.

## The Clerk test user (M5)

Every app page needs a session, so the demo signs in as a Clerk test user. Create it once in the Clerk dashboard
(Users, Create user) with an email ending in `+clerk_test`, for example `sagaloom+clerk_test@example.com`, and a
password, then add both to `web/.env.local`:

    E2E_CLERK_USER_EMAIL=sagaloom+clerk_test@example.com
    E2E_CLERK_USER_PASSWORD=<the password>

Without them the spec is **skipped** (no server starts) and the run prints `Skipping the exit demo: no Clerk test
user ...`. Nothing else loads `web/.env.local` into Playwright, so `playwright.config.ts` does it; a variable set in
the real environment wins. `e2e/global-setup.ts` calls `clerkSetup()` from `@clerk/testing/playwright`, which fetches a
testing token with `CLERK_SECRET_KEY` (and reads `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`) from `web/.env.local`, so the
browser gets past Clerk's bot protection. The demo API gets `ADMIN_EMAIL` set to the test user's email, so the test
user is the admin: the demo switches admin-only settings (the input guard, the tools), and the admin has no monthly
budget. `CLERK_ISSUER` reaches the API from the root `.env`, as for the dev API. Both servers inherit the
Playwright process's environment, so the values loaded from `web/.env.local` (`CLERK_SECRET_KEY`, `API_SHARED_SECRET`)
reach the API as real env and win over `api/.env` and the root `.env`: keep them the same.

Step 0 checks the public home page signed out (the hero line and a **Sign up free** link; not the preview, which
Next may serve from its cache), signs in with `setupClerkTestingToken` and `clerk.signIn` (password strategy), opens
`/` and waits for the redirect to `/canon`. The API starts on an empty data folder and seeds no world, so the test
user's own Velmar copy gets the id `velmar`, which step 35 checks in the World picker.

A failed run's trace in `web/test-results/` holds the test user's session and password: don't share it.

## Cost and failures

It makes **real OpenRouter calls** (and real Wikipedia calls for the reference tool in step 13; the fan-wiki step
sends none). Expect about 7 to 8 minutes and a few cents.
The API key comes from `api/.env`; the shared secret from `api/.env` and `web/.env.local`.

If the demo fails, **copy `web/test-results/` somewhere safe before you run it again**. Playwright wipes the
folder on the next run, and it holds the only trace of the failed LLM turn.

The Wave 4 step adds a new character, Mira Hale (Captain Sorn is already committed by step 4). If the agent asks a
question instead of proposing, the step fails and prints the agent's reply.

The Wave 5 step pastes three paragraphs (Brother Aldo, the Gull Market, and the three moons over the harbour) on the
Import page and clicks **Extract entries** in the Paste text card. The extractor's output varies, so the step
asserts outcomes, not exact titles: at least two cards, each with a `From paste:` line; one sky card (an update of
Sky of Velmar or a new entry) flagged against Sky of Velmar (`ent_0007`) or Ister (`ent_0012`). The extractor names
that card as it likes ("Sky of Velmar", but also "Festival night" or "Velmar"), so the step prefers a sky title and
otherwise takes a card citing those entries that offers Save as myth. Extra judge flags are fine (Ruling R17). It
saves the sky card as myth, approves one new entry, rejects the rest, then approves the re-checked myth card. If the
sky card was an update, the entry page must show **Contains imported text**; if it was a create, step 32 logs
`demo step 32: skipped (the sky card was a create)`. Step 28 reads each `From paste:` line inside `main`, so a line
elsewhere on the page cannot satisfy it. The step prints the imported cards (`demo step 28: ...`), and fails with the
card text if no sky card or no Save as myth is offered.

The Wave 7 step (33) checks hidden secrets, all in the demo's one page, because Show secrets is kept per tab:
- **33a, in step 1.** The Canon list shows 18 entry links and no `The Choir Ledger`; the header's **Show secrets**
  makes it 19, and a second click hides it again. It runs at the start because later steps commit entries (Captain Sorn
  takes the next free id, then Mira Hale and the imported entries follow), so the seed counts only hold then.
- **33b.** On `/canon/ent_0003` the Mayor's secret fact is masked (`Secret fact`, a **Show secret fact** button, no
  "Yes, at every full Ister"), and **Mentioned in** holds a `Secret entry` chip, not The Choir Ledger.
- **33c.** A new thread sends "Mayor Elsbeth Varr is sixty years old." If the agent proposes nothing, the step fails
  and prints its reply (the Wave 4 pattern). It opens Under the hood and searches the turns' Contradiction judge
  call cards for the Mayor's own check (its request names `a change to entry ent_0003`) whose request shows
  `[secret fact hidden]` (as step 7 finds the judge turn). That request lacks
  "Yes, at every full Ister" until the drawer's **Show secrets** is clicked, and hides it again on a second click. The
  model sometimes drafts more than one change, so the step rejects every card.
- **33d.** Typing `@Ister` in the composer and picking the `Ister, the red moon` option leaves `Ister, the red moon `
  in the box (plain text, nothing sent); the step then clears it.

With the drawer open there are two buttons named **Show secrets**, so the step scopes each: the header's through
`getByRole("banner")`, the drawer's through `getByRole("complementary", { name: "Under the hood" })`.

The Wave 8 step (34) asks in a new thread "Delete the Ashen Choir." If the agent proposes no delete, the step fails
and prints its reply. On the seed the Mayor (`ent_0003`) is the only entry tied to the Choir by a link alone, and
her link is secret, so with secrets hidden the delete card must contain `and 1 linked entry` and must contain
`Secret entry` (The Choir Ledger) but not `Elsbeth`. Entries that name the Choir in their text are listed (The Choir
Ledger as a `Secret entry` chip). The header's **Show secrets** makes the card name `Mayor Elsbeth Varr`; the step
hides secrets again and clicks **Reject**. It asserts text, not layout.

The M3 Wave 3 step (35) imports from a fan wiki, in its own world so Velmar is untouched (user decision, 2026-11-10):
1. On **Canon** in Velmar it counts the entry links (secrets hidden), then picks **+ New world** in the header's World
   picker, names it `Middle-earth (demo)`, clicks **Create** and checks that the new, empty world is selected.
2. On **Import** it fills the **Fan wiki** card (scoped by `getByRole("region", { name: "Fan wiki" })`) with
   `https://en.wikipedia.org/wiki/Rivendell`, `https://en.wikipedia.org/wiki/Gandalf` and
   `https://en.wikipedia.org/wiki/Shire_(Middle-earth)`, one per line, clicks that card's **Extract entries** and waits
   up to 180 s for `/review/<id>`.
3. It asserts 3 queue rows; `Licence: <licence text>` above the queue; no NC box (no `note` in the queue column); and on
   each card `Source: official (fan wiki)`. The card titles must be the manifest's titles: the Shire URL redirects, so
   that card is `The Shire`. The input URLs, titles, URLs and licence text are read from
   `api/tests/fixtures/wiki/manifest.json`, never hard-coded.
4. It approves all three with **Approve 3 with no issues** when it is offered. Otherwise it approves each card whose
   button reads **Approve**, saves a conflict or retcon card as myth when the card offers it (and approves the
   re-checked card next), or else rejects it (extra judge flags are legitimate, Ruling R17), and logs
   `demo step 35: <title> is not clean: <choice>`. It waits for **Back to Import** and a `committed as ent_…` note.
5. On **Canon** it opens **Rivendell** and checks that its **Sources** list links the manifest URL and shows the licence.
6. It fetches the world's Markdown export through the proxy (as step 14 does) and checks that the zip bytes contain the
   file name `ATTRIBUTION.md` (its contents are pinned by the API's unit tests).
7. It checks that `<data dir>/cache/wiki/` holds the same files as before the import, so no request went past the
   seeded cache to Wikipedia.
8. It switches back to Velmar and checks that its entry count is unchanged.
