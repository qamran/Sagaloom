# Exit demo (Playwright)

`exit-demo.spec.ts` walks the whole product end to end: M1 (ask, conflict, Save as myth, Under the hood),
Wave 1 (input guard), Wave 2 (reference tool, Markdown export, tool toggles) and Wave 3 (long-term memory,
the router mode chip, the highlighted agent graph).

Run it from `web/`:

    pnpm exec playwright test

It starts its own API (port 8100) and web app (port 3100) on a throwaway data folder, so it never touches
your dev servers or `data/`.

It makes **real OpenRouter calls** (and real Wikipedia calls). Expect 3-4 minutes and a few cents.
The API key comes from `api/.env`; the shared secret from `api/.env` and `web/.env.local`.

If the demo fails, **copy `web/test-results/` somewhere safe before you run it again**. Playwright wipes the
folder on the next run, and it holds the only trace of the failed LLM turn.
