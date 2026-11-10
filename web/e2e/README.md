# Exit demo (Playwright)

`exit-demo.spec.ts` walks the whole product end to end: M1 (ask, conflict, Save as myth, Under the hood),
Wave 1 (input guard), Wave 2 (reference tool, Markdown export, tool toggles) and Wave 3 (long-term memory,
the router mode chip, the highlighted agent graph), Wave 4 (the Review tab: a two-proposal batch, the
complete fact table, one submit), Wave 5 (the Import page: paste notes, review the extracted proposals, the
imported-text marker), Wave 7 (hidden secrets, the entry page, the drawer mask, `@` suggestions) and Wave 8 (the delete
card's linked-entry count). Wave 6 moved to M3.

Run it from `web/`:

    pnpm exec playwright test

It starts its own API (port 8100) and web app (port 3100) on a throwaway data folder, so it never touches
your dev servers or `data/`.

It makes **real OpenRouter calls** (and real Wikipedia calls). Expect about 6 minutes and a few cents.
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