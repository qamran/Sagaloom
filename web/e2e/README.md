# Exit demo (Playwright)

`exit-demo.spec.ts` walks the whole product end to end: M1 (ask, conflict, Save as myth, Under the hood),
Wave 1 (input guard), Wave 2 (reference tool, Markdown export, tool toggles) and Wave 3 (long-term memory,
the router mode chip, the highlighted agent graph), Wave 4 (the Review tab: a two-proposal batch, the
complete fact table, one submit) and Wave 5 (the Import page: paste notes, review the extracted proposals, the
imported-text marker).

Run it from `web/`:

    pnpm exec playwright test

It starts its own API (port 8100) and web app (port 3100) on a throwaway data folder, so it never touches
your dev servers or `data/`.

It makes **real OpenRouter calls** (and real Wikipedia calls). Expect about 5 minutes and a few cents.
The API key comes from `api/.env`; the shared secret from `api/.env` and `web/.env.local`.

If the demo fails, **copy `web/test-results/` somewhere safe before you run it again**. Playwright wipes the
folder on the next run, and it holds the only trace of the failed LLM turn.

The Wave 4 step adds a new character, Mira Hale (Captain Sorn is already committed by step 4). If the agent asks a
question instead of proposing, the step fails and prints the agent's reply.

The Wave 5 step pastes three paragraphs (Brother Aldo, the Gull Market, and the three moons over the harbour) on the
Import page and clicks **Extract entries** in the Paste text card. The extractor's output varies, so the step asserts outcomes,
not exact titles: at least two cards, each with a `From paste:` line; one sky card (an update of Sky of Velmar or a
new entry) flagged against Sky of Velmar (`ent_0007`) or Ister (`ent_0012`). The extractor names that card as it
likes ("Sky of Velmar", but also "Festival night" or "Velmar"), so the step prefers a sky title and otherwise takes a
card citing those entries that offers Save as myth. Extra judge flags are fine (Ruling R17). It saves the sky card as myth, approves one new entry, rejects the rest, then approves
the re-checked myth card. If the sky card was an update, the entry page must show **Contains imported text**. The
step prints the imported cards (`demo step 28: ...`), and fails with the card text if no sky card or no Save as myth
is offered.
