# Sagaloom M5: user accounts and a public home page — design

**Date:** 2026-11-11
**Brief item:** Course Medium 4, "Add user authentication and personalisation" (`135.md`).
**Status:** draft for the author's approval.

## 1. Intent

Sagaloom today is single-user: one shared secret between the Next.js server and the API, no accounts, and every world, thread, preference and cost total is visible to whoever opens the app. That blocks two things:

1. **The course brief.** Medium 4 is the one medium task the evaluation lists as missing (`docs/2026-11-11-1541-sprint3-evaluation.md`).
2. **Being market-competitive.** Every competitor in the README's comparison (Realmweaver, LitMemo, StoryGuard) has accounts and a public home page that sells the product before sign-up. Sagaloom has neither.

The author's decision (2026-11-11): build **private accounts per author now**, and plan **world sharing** (co-authors, players) for a later milestone. The author also asked for a **home page for logged-out visitors**, modelled on competitors, and chose a **read-only preview** (Realmweaver-style) over a static page or a live guest chat.

## 2. Goals

- G1. A visitor can sign up (email + password, or Google), confirm their email, sign in, sign out and reset a forgotten password — all through Clerk.
- G2. A logged-in author sees only their own worlds, and through them only their own threads, entries, imports, exports, memory (preferences), prompt records and cost totals. Every API route enforces this on the server; hiding things in the UI is not enough.
- G3. Each new account starts with its own copy of the demo world Velmar, so the Get Started checklist and the README walkthroughs work for every author.
- G4. Existing data survives: on the first sign-up after upgrade, every world that has no owner (today's `velmar` and any worlds the author made) is given to that first account.
- G5. A logged-out visitor landing on `/` sees a public home page with a read-only preview, and is sent to log in when they open any app page.
- G6. Personalisation, the second half of Medium 4: the author's display name in the header with an account menu, the last world they used remembered per account (server-side, so it follows them across browsers), and the existing per-world preferences (tone, genre, banned tropes, notes) now clearly belong to that author.
- G7. The data model leaves room for sharing: a world has an owner, and access is checked through one function, so a later "members" table can widen it without touching every route.

## 3. Non-goals (this milestone)

- World sharing, invitations, roles, co-editing (planned for later; see §9).
- Sign-in methods beyond email + password and Google (Clerk can add more later from its dashboard), and any self-built auth or email sending.
- Account deletion and data export of a whole account (export per world already exists).
- Pricing, plans or payment on the home page. Sagaloom has no paid plan, so the page states no price.
- Per-user developer settings. Models, system prompt, tool toggles and the guard stay app-wide (§5.5).

## 4. Anti-goals (would make this a failure even if it works)

- A logged-in author can read or change another author's world, thread, entry, preference or prompt record by guessing an id. Every id-taking route must check ownership; a missing check is a security bug, not a nit.
- A Clerk session token or the Clerk secret key appears in a log, a prompt record, the browser bundle, an API response, or Under the hood.
- The API accepts a user it did not verify itself: every request's Clerk token is checked against Clerk's public keys in the API.
- The existing approval flow, checkpoints, evals or the Playwright exit demo break. The evals call the graph directly and must keep working without accounts.
- Existing users lose data on upgrade.

## 5. Decided design

### 5.1 Where auth lives

**Clerk owns sign-in (author's decision, 2026-11-11, replacing the self-built design).** Clerk hosts identities, passwords, Google login, email confirmation and password reset, and sends those emails. Sagaloom stores no password and no session.

- **Web:** `@clerk/nextjs`. `<ClerkProvider>` in the root layout; Clerk's `<SignIn/>` and `<SignUp/>` components on `/sign-in` and `/sign-up`; `<UserButton/>` in the header (account menu, sign out, change password, manage email — all Clerk's). `clerkMiddleware` protects every app page (§5.6). Sign-in methods enabled in the Clerk dashboard: email + password (with email confirmation) and Google.
- **Proxy:** on the server, the proxy gets the user's Clerk session token (`auth().getToken()`) and forwards it to the API as `Authorization: Bearer <token>`, next to the existing `x-sagaloom-secret` (which stays: it proves the request came from our Next server). No token → the API answers 401.
- **API:** one dependency `current_user` verifies the token itself with `PyJWT[crypto]` against Clerk's public keys (JWKS fetched from `CLERK_ISSUER` in `api/.env` and cached): signature, `iss`, `exp`/`nbf`, and `azp` against the app's origin. It never trusts a user id it was merely told. Applied to every route except `GET /api/public/preview` (§5.7).
- **Users table:** `api/data/users.sqlite`, behind one store module: Clerk user id (primary key), email, display name, `is_admin`, `last_world_id`, created date. A row is created on the first verified request from a new Clerk user (email and name read from Clerk's Backend API with the user id, or from token claims if configured — builder's choice; the Clerk secret key then goes in `api/.env` too).
- **Config:** `web/.env.local`: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`. `api/.env`: `CLERK_ISSUER`, `ADMIN_EMAIL`.
- **Rate limits (Claude's call):** sign-in brute-force protection is Clerk's. Once a request carries a token, the existing turn and request limits are keyed per user (e.g. a hash of the token's `sub`) instead of per socket peer.
- **Data statement:** the README's "Your data" section now says user identities and login live at Clerk; canon, threads and prompts stay on the API server.

### 5.2 Ownership model

- `World` gains `owner_id: str | None`. `WorldRegistry.list()` takes the user and returns only that user's worlds.
- One function decides access: `can_access_world(user, world) -> bool` (today: `world.owner_id == user.id`). Every route that takes a `world_id` or a `thread_id` resolves to a world and calls it. A thread's world comes from `ThreadRegistry` (it already stores `world_id`). Not found and not yours both answer **404**, so ids cannot be probed.
- Routes to cover (from `web/routes.py`, `web/imports.py`): worlds list/create, entries list/get/mentions, export, imports (paste, file, wiki), memory get/delete, threads create/list/get, messages, decisions, runs/last, llm-log. `GET /threads` and the Review count list only threads in the user's worlds.
- **Cost totals** (`promptlog.total_usage()`, Studio Usage, Cost by step, the Feature map's cost line) are computed over the requesting user's records only. `prompt_log` gains a `user_id` column, written on every new record and backfilled in the migration through thread → world → owner, so costs of deleted threads (e.g. a failed import) still count. The admin, who pays the OpenRouter bill, gets an **All users** switch on Studio's usage panels (Claude's call, after the builder check).
- **Guard log** (`GET /guard/log`, Studio → Guardrails "Recent verdicts") shows only the user's own threads; the admin sees all.

### 5.3 Entry ids per world

Entry ids are global today (`next_entry_id` counts across the whole Chroma collection, and Chroma's record id is the entry id). Per-account Velmar copies would collide on `ent_0001`–`ent_0019`.

**Decision:** entry ids become unique **per world**. Every author's Velmar has the same ids as the README (`ent_0007`, `ent_0012`, …), so the walkthroughs stay true for everyone.

- Required behaviour: `get_entry(world_id, id)`, `upsert_entry`, `delete_entry`, `has_id` and `next_entry_id` all work within one world; two worlds may hold the same entry id; `Entry.id` as seen by the agent, tools, cards, URLs and exports does not change shape.
- The storage mechanism (for example a Chroma record id of `{world_id}/{entry_id}` with `entry_id` kept in metadata) is left to the builder, as is the one-time migration of existing records (copy with their stored embeddings; do not re-embed).
- `seed_missing`'s "ids are global" rule (b) is updated to per-world.

### 5.4 Accounts and the demo world

- Sign-up creates the user, then copies Velmar into a new world owned by them: name "Velmar", `is_demo=True`, a fresh world id (the registry's slug rule, e.g. `velmar-2`), the seed entries at their seed ids (§5.3).
- **Admin and existing data (Claude's call, after the builder check):** the admin is named by `ADMIN_EMAIL` in `api/.env`, never by sign-up order, so a stranger who signs up first on a reachable server cannot take the data. The account whose email equals `ADMIN_EMAIL` is `is_admin`, and on its first verified request (or on API start, if it already exists) every world with `owner_id` missing is assigned to it. If that account already has a demo world through the assignment (the existing `velmar`), no second copy is made. With `ADMIN_EMAIL` unset there is no admin and unowned worlds stay unowned (invisible to everyone) until it is set; the API logs a warning at start.
- `ensure_first_run` no longer creates a global Velmar at API start; seeding happens per account at sign-up.
- The Get Started checklist (`GetStarted.tsx`, `localStorage` flags) stays as it is, but its keys are prefixed with the user id so a second account on the same browser starts fresh.
- **Last world:** `users` stores `last_world_id`; the world picker reads it on load and writes it on change (`PUT /api/me` with `last_world_id`). The current `localStorage` world choice becomes a fallback only.

### 5.5 Studio and admin

Developer settings (models per role, agent temperature / max tokens / system prompt, tool toggles, guard on/off) are app-wide and stay app-wide.

- The **first account is admin** (`is_admin`, §5.4). Only an admin may call `PUT /api/settings`, `PUT /api/settings/models`; others get 403.
- Every logged-in user can open Studio. Non-admins see the same panels read-only (controls disabled, a one-line note "Only the admin can change developer settings"), and their own usage, memory and guard verdicts.
- The Feature map gains a **User accounts** card (Medium 4): Live, with a Try it link to the account menu.

### 5.5a Sign-up and monthly AI budget (author's decision, 2026-11-11)

Sign-up is **open to anyone**, and every non-admin account has a **monthly AI budget**, after StoryGuard's free-tier AI credits and LoreKeeper's 1,500 free credits.

- The budget is one app-wide amount in US$ per account per calendar month (UTC), default **$1.00**, set by the admin in Studio → Settings (`monthly_budget_usd` in developer settings). The admin account has no limit.
- Spend is the sum of the account's `prompt_log` costs this month (§5.2), the same figures the cost display shows.
- The check runs **before** a new chat turn, a decision that resumes the graph (it may re-run the check), or an import starts. A turn already running finishes even if it crosses the line. Over budget → the API answers 402 with "You've used this month's AI budget ($1.00). It resets on <date>." and the UI shows that message in place of the composer / Extract button. Reading canon, browsing, exporting and Review decisions that only reject stay available.
- The header account menu and Studio Usage show "This month: $0.23 of $1.00".
- Abuse beyond this (many throwaway accounts) is accepted for now and listed in Known limitations; Clerk's email confirmation slows it.

### 5.5b Email (author's decision, 2026-11-11: in this milestone, through Clerk)

- **Confirmation at sign-up, password reset, change password, email change:** all Clerk's, including the emails. Sagaloom sends no email and has no SMTP setting.
- **Only confirmed emails count:** Clerk's email + password sign-up requires the email to be confirmed before an account exists; Google accounts are confirmed by Google. `ADMIN_EMAIL` is matched only against a Clerk-verified primary email, so nobody can claim the admin address without its mailbox.
- **Budget notice:** in the app (the 402 message and a banner), not by email.

### 5.6 Web app

- **Routes:** `/` is the public home page when signed out and redirects to `/canon` when signed in. `/sign-in` and `/sign-up` (Clerk components, styled to match the app) are public. Every other app page (`/canon`, `/chat`, `/review`, `/import`, `/studio` and their children) is protected by `clerkMiddleware`, which sends a signed-out visitor to `/sign-in` and back afterwards; an API 401 seen by the client does the same.
- **Header:** Clerk's `<UserButton/>` (name, email, manage account, sign out) plus "This month: $x of $y" (§5.5a). The world picker lists only the user's worlds.
- **After sign-up** the author lands on Canon in their Velmar copy with the Get Started checklist.

### 5.7 Public home page (logged out)

Modelled on the competitors' public pages (research in `internal docs/competitor_analysis/`, checked 2026-11-04). Sections, top to bottom:

1. **Hero.** Name, the one-line promise from the README ("A continuity editor for your fictional world: you decide, it checks."), who it is for (authors, fan-fiction writers, solo game masters), buttons **Sign up free** and **Sign in**. (Taglines compared: StoryGuard "Your campaign remembers, so you don't have to"; LoreKeeper "Your world, remembered"; Realmweaver "It coaches. You create.")
2. **The loop** (after StoryGuard's `#loop`): four steps in a row — you state a fact → Sagaloom checks it against canon → you approve, edit, reject or save as myth → it becomes canon.
3. **Read-only preview** (after Realmweaver's `/preview`): a canned, pre-recorded Velmar example. It shows (a) a short chat exchange where the author writes "Velmar has three moons that rise together at the solstice." and (b) the resulting approval card rendered with the real `ApprovalCard` component in a read-only mode: Conflict badge citing `ent_0012`, the fact table, quotes from both sides; plus (c) three or four Velmar entries the visitor can open and read. The buttons on the card are disabled with a caption "Sign up to try it on your own world". The data comes from a static fixture served by `GET /api/public/preview` (no model call, no session). It must contain no secret entry or secret fact.
4. **Features** — four or five cards: contradiction check on every change, human approval before anything is written, myths/rumours/secrets, import your notes and fan wikis, see what every step costs.
5. **How it compares** — a short version of the README table (Sagaloom vs Realmweaver, LitMemo, StoryGuard), with the README's "not advertised" caveat and its checked date.
6. **Footer** — Sign up / Log in again, a link to the GitHub repo, "Your canon stays on the server you run it on" (the data statement from the README, shortened).

The page reuses the app's existing styles and components; no new design system.

### 5.8 Requirements and docs

- Add a new section **R21. Accounts and the home page** to `docs/requirements.md`, one row per goal above with a testable "Done when", traced to Course Medium 4; add milestone **M5** and move "User accounts and authentication" out of the Won't table.
- README: setup (create a Clerk application, the env keys, `ADMIN_EMAIL`; the admin account inherits existing data), a walkthrough for accounts and the home page, the Feature map card, the updated "Your data" statement, Known limitations (identities at Clerk, needs internet to sign in, no sharing yet, single API process still).
- `docs/review-notes.md`: a short section on the auth design and its security choices.
- Update the evaluation doc's Medium 4 row once built.

## 6. Constraints

- Stack stays: FastAPI + LangGraph + Chroma + SQLite in `api/`, Next.js in `web/`. New dependencies: `@clerk/nextjs` (web) and `PyJWT[crypto]` (api), plus `httpx` already in use for Clerk's JWKS / Backend API.
- Single API process (README "Run the API as a single process") still holds; SQLite for the users table fits that.
- Follow the repo's process: requirement IDs, a design → plan → tasks flow, GitHub issues per task in both remotes, Opus task reviews and a Fable final review.
- Existing tests keep passing; the API test fixtures gain a test user via a fake token verifier (tests never call Clerk). Evals (`api/tests/eval`) do not go through HTTP and need no change beyond §5.3.
- The Playwright exit demo signs in a Clerk test user first (Clerk's testing tokens / a dev-instance test account; builder's choice), then runs its existing steps.

## 7. Testing (what "done" looks like)

- Unit/API tests (with a local signing key standing in for Clerk's JWKS): valid token → user; missing, expired, wrong-issuer, wrong-`azp` and bad-signature tokens → 401; first request creates the users row; the shared secret is still required.
- **Isolation tests:** for every id-taking route, user B gets 404 on user A's world, thread, entry, import and memory, and B's lists and cost totals exclude A's data. These are the most important tests in the milestone.
- Migration test: data from before M5 (worlds without owner, global entry ids) is intact after the `ADMIN_EMAIL` account's first request, owned by that user, and the ids are unchanged.
- Two new accounts each get a Velmar with `ent_0012`, and an approved change in one does not appear in the other.
- Admin-only settings: non-admin gets 403 on settings writes.
- Admin email must be verified: a token whose email is not Clerk-verified never gets admin rights.
- Budget: a non-admin over this month's budget gets 402 on a new turn, a graph-resuming decision and an import; reading still works; the admin is never blocked; spend resets at the month boundary.
- Admin by `ADMIN_EMAIL`: a first sign-up with another email gets no admin rights and no unowned worlds.
- Web: middleware redirect to `/sign-in`, home page renders signed out, preview fixture has no secrets.
- Playwright: sign up → land on Canon → walkthrough 4 (conflict) still works.

## 8. Left to the builder

- Exact Chroma keying and the migration code (§5.3).
- Table layout of `users.sqlite`.
- Whether email and name come from Clerk's Backend API or custom session-token claims.
- The preview fixture's exact content, generated once from a real run and then frozen, with secrets removed.
- Home page layout details and copy beyond what §5.7 fixes.

## 9. Later (not this milestone)

World sharing (World Anvil / Kanka style): a `world_members` table with roles (co-author, reader/player), invitations, and — before any of that ships — **server-side secret stripping**, because today secrets are only masked in the browser and a shared reader would receive them from the API.
