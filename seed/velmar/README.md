# Velmar seed world

Velmar is a fog-bound harbour city with one red moon, Ister. The seed in `entries.json` has 19 entries (`ent_0001` to `ent_0019`). It is consistent by construction, so loading it needs no whole-world scan.

- Statuses: `ent_0015` (The Song of Three Moons) is a **myth**, `ent_0016` (The Drowning of Warden Vane) is a **rumour**, the Mayor's membership of the Ashen Choir (`ent_0003`) is a **secret** fact, and `ent_0019` (The Choir Ledger) is the one **secret** entry. The web app hides secret entries and facts until Show secrets is on, so the sidebar shows 18 of 19 entries.
- Load it with `sagaloom.seed.load_seed` (idempotent: fixed IDs, world `velmar`). `ensure_first_run` loads it only when no world exists.
- To add seed entries that are new since your `api/data` was created (such as `ent_0019`), stop the API and run `cd api && uv run python scripts/seed_missing.py`. It adds only the seed entries whose title is missing from `velmar`, under a fresh id if the seed id is already taken, and never overwrites an existing entry.

## Scripted proposals (`scripted_proposals.json`)

Each item is `{name, action, entry_id?, draft, expect: {conflict_ids, retcon_keys}}`.

| Name | Action | What it says | Expected result |
|---|---|---|---|
| `three_moons` | update `ent_0007` | Sky of Velmar has `Moons: Three` | Conflict with `ent_0012` (Ister, "Only light in the night sky: Ister"; the sky has one moon). Retcon on the `Moons` key of `ent_0007` (was `One (Ister)`). The Song of Three Moons (`ent_0015`) is a myth, so it is a note only, not a conflict. |
| `founding_date` | create "The Founders' Landing" | `Founded: 290 AF` | Conflict with `ent_0005` (Founding of Velmar, `Founded: 312 AF`). No retcon, since it creates a new entry. |
| `captain_sorn` | create "Captain Sorn" | Harbourmaster of Lantern Quay who refuses to sail while Ister is full | No conflicts and no retcons. She mentions Ister and Lantern Quay, but contradicts nothing. Used for the clean-approve step of the demo. |
