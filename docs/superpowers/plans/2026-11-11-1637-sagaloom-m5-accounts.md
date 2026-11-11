# Sagaloom M5: accounts (Clerk) and a public home page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Private Clerk-backed accounts (Course Medium 4) with per-author data isolation, a monthly AI budget, and a public home page with a read-only preview.

**Architecture:** Clerk signs users in on the Next.js side; the Next proxy forwards each request's Clerk session token to the FastAPI API, which verifies it itself (PyJWT + Clerk JWKS), maps it to a row in `users.sqlite`, and scopes every world/thread/entry/memory/prompt-log read to worlds the user owns. Entry ids become per-world. Developer settings stay app-wide and admin-only; the admin is the Clerk-verified `ADMIN_EMAIL`.

**Tech Stack:** FastAPI, LangGraph, Chroma, SQLite, PyJWT[crypto], httpx (API); Next.js 16, React 19, `@clerk/nextjs`, `@clerk/testing`, Vitest, Playwright (web).

**Spec:** `docs/superpowers/specs/2026-11-11-1546-sagaloom-m5-accounts-design.md`

## Global Constraints

- Every id-taking route answers **404** both for "not found" and "not yours" (spec §5.2).
- The API never trusts a user id it was told; it verifies the Clerk token: signature (JWKS from `CLERK_ISSUER`), `iss == CLERK_ISSUER`, `exp`/`nbf`, `azp == settings.web_origin` when `azp` is present (spec §5.1).
- `x-sagaloom-secret` stays required on every `/api` route, including `GET /api/public/preview`.
- No Clerk token, Clerk secret key, or session cookie in any log, prompt record, API response or the browser bundle. Only `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` may reach the browser.
- Admin = a user whose Clerk-**verified** primary email equals `ADMIN_EMAIL` (case-insensitive). Never sign-up order.
- Monthly budget: `monthly_budget_usd` in developer settings, default `1.00`, calendar month in UTC; admin unlimited; over budget → HTTP **402** with detail exactly `You've used this month's AI budget ($1.00). It resets on 2026-12-01.` (amount and date filled in; date as `YYYY-MM-DD`).
- Entry ids keep the shape `ent_NNNN` and are unique per world; every account's Velmar holds the README ids (`ent_0007`, `ent_0012`, …).
- Next.js 16: the request-interception file is **`web/proxy.ts`** (not `middleware.ts`). Read `web/node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md` and `02-guides/authentication.md` before writing web auth code, and the installed `@clerk/nextjs` README for its Next 16 setup. Do not confuse it with the existing route `web/app/api/proxy/[...path]/route.ts`.
- Config names (exact): web `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`; API `CLERK_ISSUER`, `CLERK_SECRET_KEY`, `ADMIN_EMAIL`. (API reads root `.env` and `api/.env`; the author has put `CLERK_ISSUER` and `ADMIN_EMAIL` in root `.env`. Task 3 asks the author to add `CLERK_SECRET_KEY` there too.)
- Evals (`api/tests/eval`) and existing unit tests keep passing; tests never call Clerk (fake verifier/directory).
- After any API model change run `pnpm types:gen` from the repo root and commit `web/lib/openapi.json` and `web/lib/api-types.gen.ts`; `pnpm types:check` must pass.
- Process: one GitHub issue per task in both remotes (`origin`, `sagaloom`), milestone "M5: accounts"; commits carry `Refs: #N`, the last one `Closes: #N`; work on `main`; push only when the author says.

## Review Focus

1. **A route that forgets the ownership check.** Expected: user B gets 404 on every one of A's ids. Pinned by the route-sweep test in Task 6 (`test_every_id_route_is_owner_scoped`), which enumerates `app.routes` so a new route without a check fails.
2. **Two first requests from a new user at once** (browser loads several API calls in parallel). Expected: one users row and exactly one Velmar copy. Pinned in Task 5 (`test_concurrent_first_requests_seed_once`).
3. **A Clerk account whose email is not yet verified, equal to `ADMIN_EMAIL`.** Expected: not admin, inherits nothing; becomes admin once verified. Pinned in Task 5 (`test_unverified_admin_email_gets_nothing`, `test_admin_promoted_after_verification`).
4. **Budget crossed mid-turn and the month boundary.** Expected: the running turn finishes; the next start is refused; spend from last month does not count. Pinned in Task 8 (`test_turn_already_running_is_not_cut`, `test_previous_month_spend_ignored`).
5. **Clerk token expiry during a long SSE stream** (tokens live ~60 s). Expected: a turn that started with a valid token runs to completion; only the start is verified. Pinned in Task 4 (`test_stream_outlives_token_expiry`).

---

## Wave 1 — Identity on the API

### Task 1: Per-world entry ids

**Files:**
- Modify: `api/sagaloom/store/canon.py` (record keying, `next_entry_id`, `has_id`, `get_entry`, `upsert_entry`, `delete_entry`, search result mapping)
- Modify: `api/sagaloom/graph/nodes.py:527` (`store.next_entry_id(p.world_id)`)
- Modify: `api/sagaloom/seed.py` (`seed_missing` rule (b) per world; docstring)
- Test: `api/tests/store/test_canon.py`, `api/tests/test_seed.py`

**Interfaces:**
- Produces: `CanonStore.next_entry_id(world_id: str) -> str`; `CanonStore.has_id(world_id: str, entry_id: str) -> bool`; `CanonStore.migrate_record_ids() -> int` (number of records re-keyed; idempotent). Chroma record id is `f"{world_id}/{entry_id}"`; `entry_id` and `world_id` stay in metadata; `Entry.id` is unchanged everywhere.

- [ ] **Step 1: Write failing tests** in `test_canon.py`:
  - `test_same_entry_id_in_two_worlds`: upsert `Entry(id="ent_0001", world_id="a", title="X")` and `Entry(id="ent_0001", world_id="b", title="Y")`; `get_entry("a","ent_0001").title == "X"`, `get_entry("b","ent_0001").title == "Y"`.
  - `test_next_entry_id_is_per_world`: world a holds `ent_0005`, world b empty → `next_entry_id("b") == "ent_0001"`, `next_entry_id("a") == "ent_0006"`.
  - `test_delete_only_touches_its_world`.
  - `test_migrate_record_ids_rekeys_legacy_records`: write a legacy record directly with `col.upsert(ids=["ent_0003"], …metadata world_id="velmar"…)`; `migrate_record_ids() == 1`; `get_entry("velmar","ent_0003")` returns it; a second call returns 0; the stored embedding is the same vector (no re-embed: the fake embeddings counter does not increase).
- [ ] **Step 2:** `cd api && uv run pytest tests/store/test_canon.py -v` → the new tests FAIL.
- [ ] **Step 3: Implement** the keying in `canon.py`; `migrate_record_ids` copies ids without `/` to `"{world_id}/{id}"` with their stored embeddings, documents and metadatas (`col.get(include=["embeddings","documents","metadatas"])`), then deletes the old ids. Update `nodes.py` and `seed.py` callers; `seed_missing` checks `has_id(world_id, seed_id)`.
- [ ] **Step 4:** `uv run pytest tests/store tests/test_seed.py tests/graph -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): entry ids unique per world (M5)`.

### Task 2: Users store and the User model

**Files:**
- Create: `api/sagaloom/store/users.py`
- Modify: `api/sagaloom/models.py` (add `User`; `World.owner_id: str | None = None`)
- Modify: `api/sagaloom/store/worlds.py`
- Test: `api/tests/store/test_users.py`, `api/tests/store/test_worlds.py`

**Interfaces:**
- Produces:
  - `class User(BaseModel)`: `id: str` (Clerk user id), `email: str`, `email_verified: bool`, `display_name: str`, `last_world_id: str | None = None`, `created_at: str`, `profile_checked_at: str`, plus computed `is_admin: bool` (not stored).
  - `UserRegistry(path: Path)`: `get(user_id) -> User | None`; `upsert_profile(user_id, *, email, email_verified, display_name) -> User` (creates or updates, sets `profile_checked_at`); `set_last_world(user_id, world_id: str | None) -> None`; `find_by_email(email) -> User | None`.
  - `admin_flag(user: User, admin_email: str | None) -> bool`.
  - `WorldRegistry.list(owner_id: str | None = None)`, `create(name, *, owner_id: str | None, world_id=None, is_demo=False)`, `assign_unowned(owner_id: str) -> list[str]` (ids assigned), `owned_by(owner_id) -> list[World]`.

- [ ] **Step 1: Write failing tests:** `test_upsert_then_get`, `test_email_lowercased_and_unique` (second id with same email raises `ValueError`), `test_set_last_world`, `test_admin_flag_needs_verified_matching_email` (`admin_flag` false when unverified, false when `admin_email` None, true case-insensitively); worlds: `test_list_filters_by_owner`, `test_assign_unowned_only_takes_ownerless`, `test_legacy_worlds_json_loads_with_owner_none`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `users.py` on `sqlite3` in the style of `store/threads.py` (lazy schema, `threading.Lock`, `closing`), table `users(id PRIMARY KEY, email UNIQUE, email_verified, display_name, last_world_id, created_at, profile_checked_at)`. `World.owner_id` default `None` so old `worlds.json` loads.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(api): users store and world owners (M5)`.

### Task 3: Clerk token verifier and profile directory

**Author step first:** ask the author to add `CLERK_SECRET_KEY=<the same sk_test key as web/.env.local>` to the root `.env`, then confirm presence without printing it.

**Files:**
- Create: `api/sagaloom/auth.py`
- Modify: `api/sagaloom/config.py` (`clerk_issuer: str | None = None`, `clerk_secret_key: SecretStr | None = None`, `admin_email: str | None = None`)
- Modify: `api/pyproject.toml` (`PyJWT[crypto]`)
- Test: `api/tests/test_auth.py`

**Interfaces:**
- Produces:
  - `class Claims(BaseModel)`: `sub: str`.
  - `class TokenVerifier(Protocol)`: `def verify(self, token: str) -> Claims` (raises `AuthError`).
  - `ClerkVerifier(issuer: str, web_origin: str, *, jwks_client=None)` implementing it with `jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)`, algorithm `RS256`, `leeway=5`.
  - `class ClerkProfile(BaseModel)`: `email: str`, `email_verified: bool`, `display_name: str`.
  - `class ProfileDirectory(Protocol)`: `async def fetch(self, user_id: str) -> ClerkProfile`.
  - `ClerkDirectory(secret_key: str, http: httpx.AsyncClient | None = None)`: `GET https://api.clerk.com/v1/users/{user_id}` with `Authorization: Bearer <secret>`; primary email = the address whose id equals `primary_email_address_id`; verified = its `verification.status == "verified"`; display name = `first_name last_name` stripped, else the email's local part.
  - `class AuthError(Exception)`.

- [ ] **Step 1: Write failing tests** with a locally generated RSA key and a fake JWKS client: `test_valid_token`, `test_expired_token_rejected`, `test_wrong_issuer_rejected`, `test_wrong_azp_rejected`, `test_bad_signature_rejected`, `test_missing_azp_accepted`; directory with `httpx.MockTransport`: `test_profile_uses_primary_verified_email`, `test_profile_unverified`, `test_display_name_fallback_to_email_local_part`, `test_secret_not_in_error_message` (a 500 from Clerk raises `AuthError` whose text does not contain the secret).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** `auth.py` and the config fields.
- [ ] **Step 4:** `uv run pytest tests/test_auth.py tests/test_config.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): Clerk token verification (M5)`.

### Task 4: `current_user` dependency and per-user rate-limit key

**Files:**
- Create: `api/sagaloom/web/access.py`
- Modify: `api/sagaloom/web/app.py` (`AppDeps.users`, `AppDeps.verifier`, `AppDeps.directory`, `AppDeps.user_locks: KeyedLocks`; add `Depends(current_user)` to the protected router except the public router of Task 11; default verifier/directory built from settings, or a verifier that always raises `AuthError` and logs once if `CLERK_ISSUER` is unset)
- Modify: `api/sagaloom/web/limits.py` (`client_key`: when an `authorization: Bearer` header is present, key `"user:" + sub` read from the token's unverified payload; otherwise current behaviour)
- Modify: `api/tests/web/fakes.py` (`FakeVerifier` mapping token strings to subs, `FakeDirectory`; `make_env` signs in user `"user_a"` by default via `Authorization: Bearer tok-a`, and exposes `env.as_user(token)` → a client for another user)
- Test: `api/tests/web/test_access.py`, `api/tests/web/test_limits.py`

**Interfaces:**
- Consumes: Task 2 `UserRegistry`, Task 3 `TokenVerifier`, `ProfileDirectory`.
- Produces: `async def current_user(request: Request) -> User` (dependency; stores the user on `request.state.user`); `def user_of(request) -> User`. Provisioning itself is Task 5; here `current_user` calls `ensure_user(deps, claims) -> User` defined in Task 5 as a stub that only upserts the profile.

- [ ] **Step 1: Write failing tests:** `test_no_token_401`, `test_bad_token_401`, `test_valid_token_sets_user`, `test_secret_still_required` (valid token, no shared secret → 401), `test_health_needs_nothing`, `test_stream_outlives_token_expiry` (FakeVerifier that rejects `tok-a` after the first call; a scripted turn started with it streams to `done`); limits: `test_rate_limit_keyed_per_user_behind_proxy` (two subs from the same peer do not share a bucket), `test_no_token_keyed_by_peer`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.** Token decode for the limiter key uses `jwt.decode(token, options={"verify_signature": False})` inside `try`; on failure fall back to the peer key.
- [ ] **Step 4:** `uv run pytest tests/web -v` → PASS (existing web tests pass because `make_env` signs in by default).
- [ ] **Step 5: Commit** `feat(api): current_user from Clerk tokens (M5)`.

## Wave 2 — Ownership

### Task 5: Provisioning, admin, Velmar per account, startup migration

**Files:**
- Create: `api/sagaloom/accounts.py`
- Modify: `api/sagaloom/seed.py` (`copy_velmar(store, worlds, seed_dir, owner_id) -> World`; remove `ensure_first_run` from startup use, keep `load_seed` for scripts/evals)
- Modify: `api/sagaloom/web/app.py` (`_open_runtime`: call `store.migrate_record_ids()`; if a verified admin user already exists, `worlds.assign_unowned(admin.id)`; log a warning when `ADMIN_EMAIL` is unset)
- Test: `api/tests/test_accounts.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `async def ensure_user(deps, claims: Claims) -> User`: under `deps.user_locks.hold(claims.sub)`: fetch the profile on first sight and re-fetch when `profile_checked_at` is older than 10 minutes and the email is unverified; upsert; if `admin_flag(user, settings.admin_email)`, `assign_unowned(user.id)`; if the user then owns no world, `copy_velmar(...)` and set `last_world_id` to it. Returns the user with `is_admin` set.

- [ ] **Step 1: Write failing tests:** `test_new_user_gets_own_velmar_with_readme_ids` (two users each get a demo world, `is_demo=True`, distinct world ids, both holding `ent_0012`), `test_change_in_one_velmar_not_in_other`, `test_admin_inherits_unowned_worlds` (legacy `velmar` with `owner_id=None` → owned by admin, no second copy, entry ids unchanged), `test_non_admin_first_user_gets_nothing_unowned`, `test_unverified_admin_email_gets_nothing`, `test_admin_promoted_after_verification` (directory flips to verified; after 10 minutes of fake clock the next request makes them admin and assigns), `test_concurrent_first_requests_seed_once` (`asyncio.gather` of 5 `ensure_user` calls → one demo world), `test_startup_assigns_to_existing_admin`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest tests/test_accounts.py tests/test_seed.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): account provisioning and admin (M5)`.

### Task 6: Owner-scoped routes

**Files:**
- Modify: `api/sagaloom/web/access.py` (`world_for(request, world_id) -> World`, `thread_for(request, thread_id) -> ThreadInfo`, `require_admin(request) -> User`)
- Modify: `api/sagaloom/web/routes.py` (every world/thread route uses `world_for`/`thread_for`; `list_worlds` returns `owned_by(user.id)`; `create_world` sets `owner_id`; `create_thread` checks the world; replace `_thread`)
- Modify: `api/sagaloom/web/thread_list.py` (`list_rows(deps, *, world_ids: set[str], pending, world_id, kind)` — rows outside `world_ids` are skipped; a `world_id` not in it returns `[]`)
- Test: `api/tests/web/test_isolation.py`

**Interfaces:**
- Consumes: Task 4 `user_of`, Task 2 `owned_by`.
- Produces: `world_for`, `thread_for`, `require_admin` (403 detail `Only the admin can change developer settings.`).

- [ ] **Step 1: Write failing tests:** for user B against A's resources, each → 404: worlds/{id}/entries, entries/{id}, mentions, export, imports (paste), memory GET/DELETE, threads POST with A's world, threads/{id}, messages, decisions, runs/last, llm-log. `GET /worlds` and `GET /threads` (with and without `pending=true`) return none of A's. Plus `test_every_id_route_is_owner_scoped`: iterate `app.routes`, collect paths containing `{world_id}` or `{thread_id}`, and assert each appears in the tested table (fails when a new id route is added without a test).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest tests/web -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): owner-scoped worlds and threads (M5)`.

### Task 7: Per-user prompt log, costs, guard log; admin-only settings; `/me`

**Files:**
- Modify: `api/sagaloom/promptlog.py` (column `user_id TEXT`; migration adds it and backfills through threads → worlds → owner via `backfill_user_ids(owner_of_thread: Callable[[str], str | None]) -> int`; `PromptLogHandler(..., user_id: str | None)`; `usage(..., user_id=None)`, `usage_by_model(user_id=None)`, `list_by_role(role, limit, user_id=None)`, `month_spend(user_id: str, now: datetime) -> float`)
- Modify: `api/sagaloom/web/routes.py` (`_turn_config` passes the thread's owner id; `/studio?scope=all|mine` (`all` admin-only, 403 otherwise); `/guard/log` mine, or all for admin with `scope=all`; settings `PUT`s use `require_admin`; new `GET /me`, `PUT /me`)
- Modify: `api/sagaloom/settings_store.py` (`monthly_budget_usd: float = Field(default=1.0, ge=0, le=1000)` in `DevSettings` and `DevSettingsPatch`)
- Modify: `api/sagaloom/studio.py` (feature card `accounts`: title "User accounts", status Live when `clerk_issuer` is set, detail "Sign-in by Clerk; every author sees only their own worlds.", `try_href="/canon"`; cost line uses the caller's total)
- Modify: `api/sagaloom/web/app.py` (startup calls `backfill_user_ids`)
- Test: `api/tests/test_promptlog.py`, `api/tests/web/test_me.py`, `api/tests/web/test_settings_routes.py`, `api/tests/web/test_studio_routes.py`

**Interfaces:**
- Produces: `GET /api/me` → `{"id","email","display_name","is_admin","last_world_id","month_spend_usd","monthly_budget_usd","budget_resets_on"}` (`budget_resets_on` = first day of next UTC month, `YYYY-MM-DD`; `monthly_budget_usd` is `null` for the admin). `PUT /api/me` body `{"last_world_id": str | null}` → 404 if the world is not the user's.

- [ ] **Step 1: Write failing tests:** `test_records_carry_user_id`, `test_backfill_via_thread_owner`, `test_deleted_thread_cost_still_counts_for_user` (record written with `user_id`, thread row deleted → still in `usage(user_id=…)`), `test_month_spend_window`; routes: `test_studio_usage_is_mine`, `test_studio_scope_all_admin_only`, `test_guard_log_is_mine`, `test_non_admin_settings_write_403`, `test_admin_can_set_budget`, `test_me_shape`, `test_put_me_rejects_foreign_world`, `test_feature_map_has_accounts_card`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest -q` (whole API suite) → PASS.
- [ ] **Step 5:** `pnpm types:gen` (repo root); `pnpm types:check` → clean.
- [ ] **Step 6: Commit** `feat(api): per-user costs, admin settings, /me (M5)`.

## Wave 3 — Budget

### Task 8: Monthly AI budget gate

**Files:**
- Create: `api/sagaloom/budget.py`
- Modify: `api/sagaloom/web/routes.py` (`post_message`, `post_decisions`, `post_import` call `check_budget` before taking the turn lock)
- Test: `api/tests/web/test_budget.py`

**Interfaces:**
- Produces: `def check_budget(deps, user: User, now: datetime | None = None) -> None` (raises `HTTPException(402, detail=<Global Constraints text>)`); `def budget_reset_date(now: datetime) -> date`.

- [ ] **Step 1: Write failing tests:** `test_under_budget_allowed`, `test_over_budget_402_on_message`, `…_on_decisions`, `…_on_import`, `test_402_detail_text` (budget 1.0, spend 1.0 on 2026-11-20 → detail exactly `You've used this month's AI budget ($1.00). It resets on 2026-12-01.`), `test_reads_still_work_over_budget` (entries, export, threads GET → 200), `test_admin_never_blocked`, `test_turn_already_running_is_not_cut` (spend crosses during a scripted turn; the stream ends with `done`, the next message → 402), `test_previous_month_spend_ignored`, `test_budget_zero_blocks_everything_ai`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `uv run pytest tests/web -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): monthly AI budget (M5)`.

## Wave 4 — Web app

### Task 9: Clerk in Next.js: provider, sign-in pages, `proxy.ts`, token forwarding

**Files:**
- Modify: `web/package.json` (`@clerk/nextjs`; dev `@clerk/testing`)
- Create: `web/proxy.ts` (Clerk middleware; public matcher `/`, `/sign-in(.*)`, `/sign-up(.*)`, `/api/proxy/public/(.*)`; everything else protected; page requests redirect to `/sign-in`, `/api/proxy/*` requests get 401)
- Create: `web/app/sign-in/[[...sign-in]]/page.tsx`, `web/app/sign-up/[[...sign-up]]/page.tsx`
- Modify: `web/app/layout.tsx` (`ClerkProvider`)
- Modify: `web/app/api/proxy/[...path]/route.ts` (server-side `auth()` → `getToken()` → `Authorization: Bearer`; never logs headers; no token and a non-public path → 401 JSON `{"detail":"sign in required"}` without calling the API)
- Modify: `web/lib/api.ts` (401 → `window.location.assign("/sign-in?redirect_url=" + encodeURIComponent(location.pathname))`)
- Test: `web/tests/proxyAuth.test.ts`, `web/tests/api401.test.ts`

**Interfaces:**
- Consumes: Task 4 (API expects `Authorization: Bearer <Clerk token>`).
- Produces: signed-in pages; the proxy forwards tokens.

- [ ] **Step 1:** Read the Next 16 proxy and authentication docs and the installed Clerk README (Global Constraints). Note in the issue which Clerk API names you used.
- [ ] **Step 2: Write failing tests** (Vitest, with `@clerk/nextjs/server` mocked): `forwards bearer token`, `401 without token on non-public path, API not called`, `public preview path forwarded without token`, `never copies the cookie header upstream`; `api401`: a 401 response redirects to `/sign-in` with the current path.
- [ ] **Step 3:** `cd web && pnpm vitest run tests/proxyAuth.test.ts tests/api401.test.ts` → FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5:** `pnpm vitest run && pnpm lint && pnpm build` → PASS.
- [ ] **Step 6: Manual check:** `pnpm dev` from the repo root; open http://localhost:3000/canon in Chrome → redirected to sign-in; sign up with the author's `ADMIN_EMAIL` → Canon shows the existing Velmar. Ask the author to do this sign-up themselves (it needs their mailbox).
- [ ] **Step 7: Commit** `feat(web): Clerk sign-in and token forwarding (M5)`.

### Task 10: Header, world memory, spend line, budget and read-only Studio UI

**Files:**
- Modify: `web/components/Header.tsx` (signed out: logo + "Sign in" + "Sign up free"; signed in: current nav + `<UserButton/>` + spend line `This month: $0.23 of $1.00` from `GET /me`, hidden for the admin)
- Modify: `web/lib/world.tsx` (initial world = `me.last_world_id` if it is one of the user's worlds, else the `localStorage` value, else the first; on change `PUT /me`)
- Modify: `web/lib/tour.ts` (keys prefixed `sagaloom.tour.<userId>.`)
- Modify: `web/components/Composer.tsx`, `web/app/import/page.tsx` (on 402 show the API detail in place of the input/Extract button)
- Modify: `web/components/SettingsPanel.tsx`, `ToolsPanel.tsx`, `ProvidersPanel.tsx`, `GuardrailsPanel.tsx` (disabled controls + `Only the admin can change developer settings.` when `!me.is_admin`); `SettingsPanel` gains a "Monthly AI budget (US$)" number field
- Modify: `web/components/UsagePanel.tsx` (admin-only "All users" switch → `/studio?scope=all`)
- Modify: `web/lib/api.ts`, `web/lib/types.ts` (`getMe`, `putMe`, `Me`)
- Test: `web/tests/Header.test.tsx`, `web/tests/world.test.tsx`, `web/tests/Composer.test.tsx`, `web/tests/SettingsPanel.test.tsx`

- [ ] **Step 1: Write failing tests:** header spend line text and its absence for admin; world init prefers `last_world_id`, ignores a foreign id, calls `putMe` on change; tour keys include the user id; Composer shows the 402 detail and no textarea; Settings controls disabled for non-admin and the note shown; budget field sends `monthly_budget_usd`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4:** `pnpm vitest run && pnpm lint && pnpm build` → PASS.
- [ ] **Step 5: Commit** `feat(web): account header, world memory, budget UI (M5)`.

## Wave 5 — Public home page

### Task 11: Preview fixture and public route

**Files:**
- Create: `api/sagaloom/public/preview.json`, `api/sagaloom/public/__init__.py`
- Create: `api/sagaloom/web/public_routes.py` (`GET /api/public/preview`, behind the shared secret only, no `current_user`)
- Modify: `api/sagaloom/web/app.py` (mount the public router on the secret-only router)
- Create: `api/scripts/make_preview_fixture.py` (reads a real thread's state + Velmar entries from a data dir, drops every secret entry and secret fact, writes the JSON)
- Test: `api/tests/web/test_public_preview.py`

**Interfaces:**
- Produces: response `{"messages":[{role,content}...], "pending_interrupt":{"proposals":[...],"checks":[...]}, "entries":[Entry...]}` — the same shapes `GET /threads/{id}` and `GET /worlds/{id}/entries` return, so the web reuses its types.

- [ ] **Step 1: Write failing tests:** `test_preview_needs_secret_not_user`, `test_preview_has_conflict_with_ent_0012`, `test_preview_has_no_secrets` (no entry `status == "secret"`, no fact with `status == "secret"`, and the strings `Choir Ledger` and the Mayor's secret fact value do not occur anywhere in the JSON), `test_preview_makes_no_model_call`.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Generate the fixture: run walkthrough 4 ("Velmar has three moons that rise together at the solstice.") once on the dev server with the author's account, then `uv run python scripts/make_preview_fixture.py <data_dir> <thread_id>`; pick 4 entries: Sky of Velmar, Ister (`ent_0012`), Lantern Quay, Harbour Council.
- [ ] **Step 4:** run → PASS.
- [ ] **Step 5: Commit** `feat(api): public preview fixture (M5)`.

### Task 12: Home page

**Files:**
- Modify: `web/app/page.tsx` (signed in → `redirect("/canon")`; signed out → `<HomePage/>`)
- Create: `web/components/home/HomePage.tsx`, `Hero.tsx`, `Loop.tsx`, `Preview.tsx`, `Features.tsx`, `Compare.tsx`
- Modify: `web/components/ApprovalCard.tsx` (`readOnly?: boolean`: actions disabled, caption `Sign up to try it on your own world`)
- Modify: `web/lib/api.ts` (`getPreview`)
- Test: `web/tests/HomePage.test.tsx`, `web/tests/ApprovalCard.test.tsx`

Copy fixed by the spec (§5.7): hero line `A continuity editor for your fictional world: you decide, it checks.`; audience `For authors, fan-fiction writers and solo game masters.`; buttons `Sign up free` → `/sign-up`, `Sign in` → `/sign-in`; loop steps in order: `You state a fact` → `Sagaloom checks it against canon` → `You approve, edit, reject or save it as a myth` → `It becomes canon`; compare table rows from README "How Sagaloom compares" (first three rows) with the caveat line and "checked 2026-11-04"; footer `Your canon stays on the server you run it on.` and the GitHub link `https://github.com/qamran/Sagaloom`.

- [ ] **Step 1: Write failing tests:** renders hero copy and both buttons with hrefs; loop has 4 steps in order; preview shows the Conflict badge and `ent_0012`, its buttons are disabled with the caption; preview entries open read-only; no element links into app pages except sign-in/up; `ApprovalCard readOnly` disables all actions.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** with the existing Tailwind tokens and components; layout must work at 375 px width.
- [ ] **Step 4:** `pnpm vitest run && pnpm lint && pnpm build` → PASS.
- [ ] **Step 5: Manual check** signed out in Chrome at http://localhost:3000 (desktop and a narrow window); screenshot for the issue.
- [ ] **Step 6: Commit** `feat(web): public home page with read-only preview (M5)`.

## Wave 6 — Demo, docs, requirements

### Task 13: Playwright exit demo signs in

**Files:**
- Modify: `web/playwright.config.ts` (load Clerk keys; `globalSetup` calling `clerkSetup()` from `@clerk/testing/playwright`)
- Modify: `web/e2e/exit-demo.spec.ts` (first step: home page visible signed out → sign in as the test user via `setupClerkTestingToken` and `clerk.signIn` with `E2E_CLERK_USER_EMAIL`/`E2E_CLERK_USER_PASSWORD`; skip the spec with a clear message when those are unset; then the existing steps)
- Modify: `web/e2e/README.md`

**Author step:** create a test user in the Clerk dashboard (Users → Create user) with an email ending `+clerk_test@<anything>` and a password; put `E2E_CLERK_USER_EMAIL` and `E2E_CLERK_USER_PASSWORD` in `web/.env.local`.

- [ ] **Step 1:** Update config and spec (check the installed `@clerk/testing` README for the exact helper names).
- [ ] **Step 2:** `cd web && pnpm exec playwright test` → PASS (real model calls).
- [ ] **Step 3: Commit** `test(web): exit demo signs in through Clerk (M5)`.

### Task 14: Requirements, README, review notes, evaluation

**Files:**
- Modify: `docs/requirements.md` (section **R21. Accounts and the home page**: R21.1 sign-in via Clerk; R21.2 token verified by the API; R21.3 owner-scoped data (404); R21.4 per-world entry ids; R21.5 Velmar per account; R21.6 admin by verified `ADMIN_EMAIL` inherits unowned worlds; R21.7 admin-only developer settings; R21.8 monthly AI budget; R21.9 personalisation (header, last world); R21.10 public home page with read-only preview — each with Priority, Source "Course (Medium 4)", and "Done when" + test names as evidence; milestone M5; remove the Won't row; bonus table adds Medium 4; decision log entries for Clerk, budget, `ADMIN_EMAIL`)
- Modify: `README.md` (Setup: Clerk application, the four env names and where they go, `ADMIN_EMAIL`, first sign-in; walkthrough 17 "Accounts and the home page"; Reviewer's tour step 0 sign up; Course bonus table Medium 4 row; "Your data" now names Clerk; Known limitations: identities at Clerk, sign-in needs internet, budget per account but throwaway accounts possible, no sharing yet)
- Modify: `docs/review-notes.md` (§14 Accounts: why Clerk, token verification in the API, 404 for foreign ids, admin by verified email, budget; fix §1 "up to six" → seven tools)
- Modify: `docs/2026-11-11-1541-sprint3-evaluation.md` (Medium 4 → Done with where/how to test; counts become 13 of 18, 7 medium)

- [ ] **Step 1:** Write the changes.
- [ ] **Step 2:** Check every test name cited as evidence exists: `cd api && uv run pytest --collect-only -q | grep -c <name>` for each.
- [ ] **Step 3: Commit** `docs: M5 accounts requirements, README, review notes (M5)`.

---

## Execution notes

- Issues: create one per task (14) in `origin` and `sagaloom`, same order, milestone "M5: accounts", before Task 1.
- Builders: Sonnet for Tasks 2, 3, 8, 10, 11, 12, 13, 14; Opus for Tasks 1, 4, 5, 6, 7, 9. Every task reviewed by a fresh Opus reviewer against the spec; Fable reviews each wave and the whole milestone.
- After each wave: `cd api && uv run pytest -q`; `cd web && pnpm vitest run && pnpm lint && pnpm build`; `pnpm types:check`. Evals and Playwright once at the end of Wave 6.
