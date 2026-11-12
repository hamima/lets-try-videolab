# Gmail Sign-In, Per-User Workspaces, and Admin-Gated Settings

VidLife currently has zero authentication of any kind — every route, including Settings, is open to anyone who can reach the app, and workspaces live at `workspace/<domain>/<run_id>/` with no concept of "who owns this." This plan adds a sign-in step to the front of the app, restricted to `@gmail.com` accounts, and uses that identity to (a) gate the Settings tab to an admin allowlist and (b) scope every run/workspace to the user who created it.

## Key decisions from planning

- **Auth is Google Sign-In, restricted to literal `@gmail.com` addresses** — not Google Workspace domains. The backend rejects any verified email whose domain isn't `gmail.com`.
- **User-id = the email's local-part, used as-is.** `hamidreza.maghbooli@gmail.com` → `hamidreza.maghbooli`. No further normalization. This id is both the session's identity and the workspace folder name.
- **New workspace layout: `workspace/<user>/<domain>/<run_id>/`** — user-first, so "list this user's runs" is a single directory listing instead of a filter across every domain folder.
- **Migration of existing workspaces is a one-time script**, not permanent backend logic. After it runs once, the codebase only ever knows about the new layout.
- **The backend cryptographically verifies Google's ID token** (via the `google-auth` library) rather than trusting a client-asserted email — this is the only approach that actually delivers "people can only watch their own workspaces," since a trust-the-client approach would let anyone spoof any email.
- **Sessions are an in-memory store** (`{session_id: email}`, matching the existing `_active_runs` in-memory pattern in `backend/tasks.py`) behind an opaque HttpOnly cookie. Lost on backend restart — acceptable for how this app runs today (single local/small-scale process, no load balancer).
- **`admins.conf`** — plain text, one full Gmail address per line, `#`-comments allowed, at the project root (alongside `settings.json`).
- **The whole app requires sign-in.** Unauthenticated visitors see only a dedicated `/signin` page; every other route redirects there until authenticated.
- **Admins see every user's workspaces**; everyone else sees only their own. One `is_admin` flag unlocks both the Settings tab and full workspace visibility.
- **Non-owner access to a run returns 404**, not 403 — doesn't leak whether a given `domain/run_id` exists at all.
- **Sign-in is open to any `@gmail.com` account** — no separate allowlist beyond `admins.conf`. First login silently gets its own (initially empty) workspace folder.
- **Admin run cards show an owner badge** on the Pipeline list page, since admins see everyone's runs mixed together.
- **Admin access to another user's run uses a query param**: `/tasks/:domain/:runId?owner=<user-id>`, honored only when the caller is an admin — the route shape stays the same for everyone, non-admins just never need (or get to use) the param.

## UI samples

Rough text mockups of the new/changed screens, to anchor the decisions above before implementation.

### `/signin` — dedicated sign-in page

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                        │
│                                                                        │
│                                                                        │
│                          VidLife                                      │
│                 Sign in to view your pipeline runs                    │
│                                                                        │
│                   ┌───────────────────────────┐                       │
│                   │  G  Sign in with Google    │                       │
│                   └───────────────────────────┘                       │
│                                                                        │
│                  Only @gmail.com accounts are supported.              │
│                                                                        │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

No nav bar, no app chrome — just branding and the Google button, per the "dedicated page, not a modal" decision. An inline error (e.g. "Only @gmail.com accounts are supported") replaces the helper line below the button if sign-in fails or a non-Gmail account is used.

### Nav header — signed out vs. signed in (non-admin)

Visiting any route signed out immediately redirects to `/signin` (no header renders at all). Once signed in, the header gains a user indicator + sign-out on the right; note there's **no Settings link** for a non-admin:

```
┌──────────────────────────────────────────────────────────────────────┐
│  VidLife          Generate   Pipeline              h.maghbooli ▾      │
└──────────────────────────────────────────────────────────────────────┘
                                                      ┌───────────────┐
                                                      │ h.maghbooli   │
                                                      │ @gmail.com    │
                                                      │ ─────────────  │
                                                      │ Sign out       │
                                                      └───────────────┘
```

### Nav header — signed in as admin

Same header, but with the Settings link restored (gated client-side by `isAdmin`, enforced server-side regardless):

```
┌──────────────────────────────────────────────────────────────────────┐
│  VidLife    Generate   Pipeline   Settings      hamidreza.maghbooli ▾ │
└──────────────────────────────────────────────────────────────────────┘
```

### Pipeline list — admin view with owner badges

Non-admins see exactly today's card grid (their own runs only, no owner indicator). Admins see every user's runs, each card additionally tagged with its owner:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Pipeline Runs                                                        │
│  15 workspaces across all domains, all users              [+ New Run]│
├───────────────────────────┬───────────────────────────┬──────────────┤
│ political          Partial│ political            Done │ general   … │
│ 👤 hamidreza.maghbooli     │ 👤 priya.k                 │ 👤 j.vandermeer│
│ Oct 20, 02:43 PM           │ Oct 9, 11:35 AM            │ Sep 9       │
│ ████████░░ 10/18 steps     │ ██████████ 18/18 steps     │ █░░░░ 1/18  │
└───────────────────────────┴───────────────────────────┴──────────────┘
```

Clicking a card owned by someone else navigates to `/tasks/political/2026-10-20_144349?owner=hamidreza.maghbooli` — the `owner` query param is pre-filled by the card's link and only has any effect because the viewer is an admin (see "Add ownership resolution" below).

### Settings — blocked for non-admins

A non-admin who manually navigates to `/settings` (no nav link, but a bookmarked/typed URL) is redirected away before the page ever renders; the backend independently 403s the underlying `GET/PUT /tasks/settings` calls regardless of what the frontend does:

```
non-admin visits /settings
        │
        ▼
 redirect to / (no Settings page ever mounts)
```

## Add Google Sign-In on the frontend

Build the actual sign-in UI and the client side of the auth flow.

### Set up a Google Cloud OAuth Client ID

This is a manual one-time setup step in Google Cloud Console (outside the codebase): create an OAuth 2.0 Client ID for a Web application, add `http://localhost:5173` (and any deployed origin) as an authorized JavaScript origin. No client secret is needed — the "Sign in with Google" button flow (Google Identity Services) returns a signed ID token directly to the frontend, verified later by the backend using only the Client ID (checked against the token's `aud` claim).

#### Acceptance criteria
- Document this as a manual prerequisite step in `docs/authentication.md` itself (this file) and/or `docs/web.md`, including where the resulting Client ID needs to go (see next subtask).

### Add the Google Identity Services button and `/signin` page

Add `frontend/src/pages/SignInPage.tsx`, routed at `/signin`, rendering nothing but branding and the Google Sign-In button (loaded via the Google Identity Services script, `https://accounts.google.com/gsi/client`). On successful sign-in, Google calls back with a signed ID token (JWT); POST it to a new backend endpoint (`POST /tasks/auth/google`, body `{ credential: <id_token> }`).

The Client ID itself is a public (non-secret) value needed by the frontend at build time — add it as `VITE_GOOGLE_CLIENT_ID` in `frontend/.env.local`, following the existing `VITE_*` convention already used for `VITE_MOCK`/`VITE_MOCK_TASKS`.

#### Acceptance criteria
- Visiting `/signin` while already authenticated redirects straight to `/`.
- A failed/rejected Google sign-in (e.g. user cancels) shows an inline error, no partial session created.
- A successful callback POSTs the credential and, on a 200 response, redirects to `/` (or wherever the user originally tried to go — see the route-guard subtask below).

### Add a backend sign-in endpoint that verifies the token and starts a session

Add `POST /tasks/auth/google` to `backend/tasks.py`. Verify the posted ID token using `google.oauth2.id_token.verify_oauth2_token` (from the `google-auth` package — add it to `backend/requirements.txt`), checking:
- Signature validity against Google's public keys.
- `aud` claim matches the configured Client ID.
- `email_verified` is true.
- The email's domain is exactly `gmail.com` — otherwise reject with a clear error (e.g. 403, `"Only @gmail.com accounts are supported"`).

On success: derive the user-id as the email's local-part (everything before `@`, used as-is), generate a random opaque session id, store `{session_id: {email, user_id}}` in an in-memory dict (same pattern as `_active_runs`), and set it as an HttpOnly, `SameSite=Lax` cookie. Return `{email, user_id, is_admin}` in the response body (see the admin task for `is_admin`).

Also add `GET /tasks/auth/me` (returns the current session's `{email, user_id, is_admin}`, or 401 if no valid session) and `POST /tasks/auth/logout` (clears the session server-side and expires the cookie).

The Client ID the backend uses for `aud` verification goes in `settings.json` (same file as the other provider keys) as `GOOGLE_CLIENT_ID` — this is a bootstrap value set manually before first use, same as `GEMINI_API_KEY` etc. are today.

#### Acceptance criteria
- A token with a bad signature, wrong audience, unverified email, or non-gmail.com domain is rejected and no session is created.
- A valid token creates a session and sets the cookie; `GET /tasks/auth/me` afterward returns the right identity.
- `POST /tasks/auth/logout` actually invalidates the session — a subsequent `GET /tasks/auth/me` returns 401.
- New unit tests in `backend/tests/` covering the email-domain rejection and the happy path (can stub/mock `verify_oauth2_token`).

## Gate the whole frontend app behind sign-in

### Add a current-user context and a route guard

Add a small `AuthContext`/hook (`frontend/src/lib/auth.tsx` or similar) that calls `GET /tasks/auth/me` on mount and exposes `{ user, isAdmin, loading }`. Wrap the app's routes (in `App.tsx`) so that every route except `/signin` requires `user` to be set — redirect to `/signin` otherwise, preserving the originally-requested path so sign-in can redirect back to it.

#### Acceptance criteria
- Visiting any route while unauthenticated (fresh browser, no cookie) redirects to `/signin`.
- After signing in, the user lands back on the page they originally tried to visit (not always `/`).
- While the initial `GET /tasks/auth/me` check is in flight, show a loading state rather than flashing protected content or prematurely redirecting.

### Add a signed-in indicator and sign-out to the nav header

In `Layout.tsx`'s header, add a small user indicator (email or derived initials) on the right, with a sign-out action that calls `POST /tasks/auth/logout` and redirects to `/signin`.

#### Acceptance criteria
- The indicator reflects the currently signed-in user's email.
- Clicking sign-out clears the session (verify via `GET /tasks/auth/me` returning 401 afterward) and lands on `/signin`.

## Add the admin role and gate Settings

### Add `admins.conf` and an `is_admin` check

Add `admins.conf` at the project root: plain text, one full Gmail address per line, `#`-comments and blank lines ignored. Add a small backend helper (e.g. `_is_admin(email: str) -> bool`) that reads and checks membership against this file (re-read per call or cached with a simple mtime check — no need for anything fancier given file size). Wire this into the session endpoints so `is_admin` is accurate in `/tasks/auth/me` and the sign-in response.

#### Acceptance criteria
- An email present in `admins.conf` (exact match) gets `is_admin: true`; everyone else gets `false`.
- Comments/blank lines in `admins.conf` don't break parsing.
- A unit test covering the parser (comments, blank lines, trailing whitespace).

### Gate the Settings tab, frontend and backend

Frontend: in `Layout.tsx`, only render the "Settings" `NavLink` when `isAdmin` is true (from the auth context). Also guard the `/settings` route itself (redirect non-admins away, e.g. to `/`) — hiding the nav link alone isn't real gating.

Backend: `GET /tasks/settings` and `PUT /tasks/settings` (in `backend/settings.py`/`tasks.py`) must check `is_admin` for the current session and return 403 if not — this is the real enforcement; the frontend hiding is just UX.

#### Acceptance criteria
- A non-admin never sees the Settings nav link, and manually navigating to `/settings` redirects them away.
- A non-admin's direct `GET`/`PUT` to `/tasks/settings` (e.g. via curl) gets 403, regardless of what the frontend shows.
- An admin can still read/write settings exactly as before.

## Scope workspaces per user

This is the core of "people can only watch the workspaces belonging to themselves" — touches workspace path construction and every run-scoped endpoint.

### Change workspace path construction to `<user>/<domain>/<run_id>`

In `backend/tasks.py`, update `new_workspace`, `latest_workspace`, and `find_workspace` (currently building `WORKSPACE_ROOT / domain / run_id` — see `tasks.py:153-174`) to take the current user's id and build `WORKSPACE_ROOT / user_id / domain / run_id` instead. Every caller of these functions needs the current user threaded through (from the session, via a FastAPI dependency — e.g. `current_user: str = Depends(get_current_user)`).

#### Acceptance criteria
- Starting a new run creates it under the signed-in user's own folder.
- `find_workspace` for a non-admin never resolves outside that user's own folder, even if asked for a `domain/run_id` that exists under a different user.

### Add ownership resolution with the admin `owner` query-param escape hatch

Add a small resolver (e.g. `_resolve_workspace(current_user, domain, run_id, owner_param)`) used by every run-scoped endpoint:
- If `current_user.is_admin` and `owner_param` is provided, resolve under that `owner_param`'s folder.
- Otherwise, always resolve under `current_user`'s own folder — `owner_param` is silently ignored for non-admins (never trust it as an override).
- If the resolved path doesn't exist, raise 404 (not 403) — matching the earlier decision not to leak existence.

Apply this to every run-scoped route currently taking `(domain, run_id)`: `get_run_status`, `run_step`, `get_step_content`, `update_step_content`, `delete_run`, `continue_run`, `serve_file`, and the asset-regeneration/animation/upload endpoints (all currently calling `find_workspace` directly per the earlier exploration — `tasks.py` lines 1121, 1153, 1192, 1212, 1650, 1866, 1911, 1935, 1961, 2037, 2071 and others).

Update `frontend/src/api/tasks.ts` so the relevant calls pass through an optional `owner` param (only ever set by the admin-only UI path described below), and update `RunDetailPage.tsx`/`RunWizardPage.tsx` to read `?owner=` from the URL via `useSearchParams` and forward it.

#### Acceptance criteria
- A non-admin hitting any run-scoped endpoint for another user's `domain/run_id` gets 404.
- An admin passing `?owner=<other-user>` successfully reaches that user's run; omitting it resolves to the admin's own workspace as normal.
- A non-admin's `owner` param (if present) has zero effect — confirmed via a test that passes `owner=someone-else` as a non-admin and still gets scoped to themselves (or 404, never someone else's data).

### Scope the runs list and add the owner badge for admins

`list_runs` (backing `TasksListPage.tsx`) must only aggregate the current user's own `workspace/<user>/` folder for non-admins, and every user's folder (with an `owner` field added per run summary) for admins. Update `RunSummary` in `frontend/src/api/tasks.ts` to include an optional `owner: string`, and `TasksListPage.tsx` to render a small owner badge on each card only when `isAdmin` is true, linking into the run detail page with `?owner=<owner>` pre-filled.

#### Acceptance criteria
- A non-admin's Pipeline list only ever shows their own runs, no owner badge.
- An admin's Pipeline list shows every user's runs with a visible owner badge, and clicking a card someone else owns correctly opens that run (via the `owner` query param) instead of 404ing.

## Migrate existing workspaces

### Write and run the one-time migration script

Add a standalone script (e.g. `scripts/migrate_workspaces_to_users.py`, not wired into any ongoing backend logic) that moves every existing `workspace/<domain>/<run_id>/` folder to `workspace/hamidreza.maghbooli/<domain>/<run_id>/` — i.e., attributes all current runs to the one real user today. Run it once, by hand, after the new path-construction code lands but is confirmed working against a fresh empty `workspace/`, then before relying on existing runs again.

#### Acceptance criteria
- Dry-run mode (default, or a `--dry-run` flag) prints what it would move without touching anything.
- Actually running it moves every `workspace/<domain>/<run_id>/` under `workspace/hamidreza.maghbooli/<domain>/<run_id>/`, preserving all file contents.
- After migration, the app (signed in as `hamidreza.maghbooli@gmail.com`) sees every pre-existing run exactly as before, just now correctly scoped to that account.
- The script is a one-off tool, not imported or called by `backend/tasks.py`/`automate.py` — no permanent migration logic ships in the running app.
