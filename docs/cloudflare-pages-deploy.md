# Deploy the Frontend to Cloudflare (Workers Static Assets, Free Plan)

**Naming note**: as of late 2026, creating a new static-site project in the Cloudflare dashboard no longer goes through "classic Pages" — it's unified into **Workers Builds**, and a pure static SPA with no server code deploys as a **Worker with static assets**, not a "Pages project" in the old sense. Everything about the free-tier economics and end result is the same (static hosting, no cold starts, a `*.workers.dev` URL instead of `*.pages.dev`); only the dashboard flow and `wrangler.jsonc` config keys differ from older Cloudflare Pages docs/tutorials — this doc went through two corrections while being written for exactly that reason, so treat anything about "Pages" elsewhere (including older parts of this repo's own history) as describing the same destination via the previous UI.

The frontend (`frontend/`) is a static Vite + React SPA — `npm run build` already produces a plain `dist/` folder with no server-side rendering or API routes of its own (all `/tasks/*` and `/api/*` calls go to the separately-deployed backend, see `docs/deployment-oracle-cloud.md`). Static-asset hosting on Cloudflare is free with no bandwidth limit and generous build/file limits (500 builds/month, 20-minute build timeout, 100 custom domains/project, 20,000 files/site, 25MiB max per file — per Cloudflare's docs, last modified 2026-09-05) — all comfortably enough for this app's single-page bundle. This app has no Worker script logic (no auth-at-the-edge, no API routes served from the Worker itself), so none of the actual Workers compute limits (CPU time, request counts) apply either — it's pure static-file serving.

This repo is a **monorepo** (`frontend/`, `backend/`, `scripts/`, etc. all siblings at the root) — the dashboard needs an explicit **root directory** setting for this, and it's the single most commonly-missed step (tucked under "Advanced settings"): miss it, and the build runs from the repo root instead, which has no `package.json`/`index.html` at all, or silently serves the wrong thing. This plan calls it out explicitly as its own task rather than folding it into generic setup.

**Key decisions:**

- **Git integration (GitHub), not CLI-only deploys.** Connects directly to this repo's GitHub remote (`git@github.com:hamima/lets-try-videolab.git`) — every push to `main` triggers an automatic build/deploy, matching the git-push-driven workflow already used for the backend (Oracle VM: `git pull && docker compose up -d --build`). Manual `wrangler deploy` stays available as a documented fallback (last task) for one-off deploys without pushing, but isn't the primary path.
- **Root directory: `frontend`.** Build command `npm run build` (already `tsc -b && vite build` per `package.json`).
- **Static assets are configured via `frontend/wrangler.jsonc`'s `assets` block, not a dashboard field** — the dashboard's build-config screen for this flow has **Deploy command** and **Preview command** fields instead, both required: `npx wrangler deploy` and `npx wrangler versions upload` respectively (Cloudflare's own stated defaults for this field). `wrangler.jsonc` has no `main` (no actual Worker script — pure static SPA) and sets `assets.directory: "./dist"` plus `assets.not_found_handling: "single-page-application"` for client-side routing. (An earlier draft of this file used `pages_build_output_dir`, which is a *different*, Pages-specific config key that does nothing in this Worker-based flow — corrected once this was actually tested against the real dashboard form.)
- **Node version is pinned explicitly**, not left to Cloudflare's build-image default (which may be older than this project's Vite 8 / TypeScript toolchain expects) — via a committed `.node-version` file, which Cloudflare's build system auto-detects.
- **`VITE_API_URL` and `VITE_GOOGLE_CLIENT_ID` are set as Cloudflare dashboard environment variables, not committed into `frontend/.env.production`.** Both are deployment-specific (the backend's actual public URL, an OAuth Client ID tied to this exact origin) — `.env.production`'s existing placeholders for these stay commented out/empty, consistent with how that file already documents them as "fill in per deployment." `VITE_MOCK`/`VITE_MOCK_TASKS=false` already live in the committed `.env.production` and need no dashboard override.
- **SPA routing is `wrangler.jsonc`'s `not_found_handling: "single-page-application"` only — `frontend/public/_redirects` had to be deleted.** It previously held the Render/Netlify-style catch-all rule (`/* /index.html 200`), and Workers static assets does support `_redirects`' syntax in general — but that specific catch-all rule fails deploy entirely with `[code: 100324] Infinite loop detected in this rule`, because Cloudflare's redirect validator sees `/*` also matching the rule's own `/index.html` destination. This is a well-documented, repeatedly-hit issue (confirmed via multiple real-world fixes on GitHub) with one standard resolution: delete the file, rely solely on `not_found_handling` instead — which is a distinct, non-redirect-based fallback mechanism at the asset-serving layer, not subject to the same loop check.
- **This plan ends with a "close the loop" task**, not left implicit: once Cloudflare assigns the real deployed URL, two things elsewhere need updating to actually work together — the backend's `ALLOWED_ORIGINS` (Oracle VM's `.env`, needs a container recreate) and the Google OAuth Client ID's authorized JavaScript origins (Google Cloud Console) — both already documented as prerequisites in `docs/authentication.md`/`docs/deployment-oracle-cloud.md`, but easy to forget once the frontend itself is "deployed."

## Create and configure the Cloudflare project

### Connect the repo

In the Cloudflare dashboard: **Workers & Pages → Create → Connect to Git** (or **Import a repository**, naming/placement of this entry point has shifted along with the Pages→Workers Builds unification — look for "deploy from Git" rather than a dedicated "Pages" button specifically). Authorize/select the `hamima/lets-try-videolab` GitHub repo, branch `main`.

### Set the monorepo root directory and build settings

Under **Settings → Build** (or the build-config step during initial setup):

- **Root directory**: `frontend`
- **Build command**: `npm run build`
- **Deploy command**: `npx wrangler deploy`
- **Preview command**: `npx wrangler versions upload`
- Framework preset: select **Vite** if offered — it pre-fills the build command, but the root directory still has to be set explicitly regardless of preset (the preset doesn't know this is a monorepo).

### Add `frontend/wrangler.jsonc`

```jsonc
{
  "name": "try-videolab",             // must match the Cloudflare project's name exactly
  "compatibility_date": "2026-11-18",
  "assets": {
    "directory": "./dist",                          // relative to frontend/, matches vite build's output
    "not_found_handling": "single-page-application"  // unmatched routes get index.html (200), not a 404
  }
}
```

No `main` field — there's no actual Worker script, this is pure static-asset serving. `name` must exactly match whatever the project was named when it was created in the Cloudflare dashboard.

#### Acceptance criteria

- The first build actually runs `npm run build` inside `frontend/` (visible in the build log's working directory), not the repo root.
- The deploy step (`npx wrangler deploy`) succeeds and reports uploading static assets from `dist/`, not "Missing entry-point to Worker script" (that error means `wrangler.jsonc`'s `assets` block wasn't picked up, or a stale `main` field is still pointing at a non-existent script).
- The deployed site actually renders the app (not a 404 or the raw repo README) — confirms the root directory took effect too, not just that a build happened.

### Pin the Node version

Add `frontend/.node-version` containing the Node major version this project is developed against (matching `frontend/package.json`'s toolchain — no `engines` field exists yet to cross-check against, so use whatever version `nvm current`/`node --version` reports in the active dev environment). Cloudflare's build image auto-detects this file and uses the matching Node version instead of its own default.

#### Acceptance criteria

- The build log shows the pinned Node version being used, not a mismatched default.

## Configure environment variables

In **Settings → Variables and Secrets** for the project, for the **Production** environment (and **Preview**, if preview deploys on branches/PRs are desired against the same backend):

- `VITE_API_URL` — the backend's real public HTTPS URL (from `docs/deployment-oracle-cloud.md`'s TLS setup — Cloudflare Tunnel or Caddy, whichever was chosen there). Must be `https://`, not `http://` — a `https://` deployed site calling a plain `http://` backend gets blocked as mixed content by the browser regardless of CORS config.
- `VITE_GOOGLE_CLIENT_ID` — only needed here if it differs from `frontend/.env.production`'s committed default (it won't have one, since that file leaves it as a placeholder) — otherwise sign-in fails with the same "not configured" error `SignInPage.tsx` already surfaces gracefully.

Trigger a rebuild after setting these (Cloudflare env var changes don't retroactively apply to already-built deploys) — either push an empty commit or use the dashboard's "Retry deployment."

#### Acceptance criteria

- `GET`-ing the deployed site and opening the browser's network tab shows API calls going to the configured `VITE_API_URL`, not a relative `/tasks` path 404ing against Cloudflare's own static host.
- Changing either dashboard env var and retriggering a build actually changes the resulting bundle's behavior (confirms they're truly build-time, matching the existing `VITE_API_URL` documentation in the root `README.md`).

## Verify SPA routing and the first real deploy

### Confirm `not_found_handling` actually covers deep-link routes

After the first successful deploy, directly load (not navigate from the homepage) a deep client-side route — e.g. `https://<project>.workers.dev/tasks` or `/tasks/<domain>/<run-id>` — both as a hard URL load and as a page refresh once already on it. This is exactly the class of bug already fixed once for the Vite dev proxy (`/tasks/*` 404ing on hard refresh) and for Netlify-style static hosts (the now-deleted `frontend/public/_redirects`) — confirm `wrangler.jsonc`'s `not_found_handling: "single-page-application"` actually covers it on Cloudflare, since it's a different mechanism than both of those.

#### Acceptance criteria

- A hard-loaded `/tasks` URL (no prior client-side navigation) renders the app, not Cloudflare's default 404 page.
- A browser refresh while on `/tasks/<domain>/<run-id>` also renders correctly.

## Close the loop — wire the real deployed URLs together

Two things elsewhere in the stack need the deployed project's actual URL before the deployed frontend can fully work, not just load:

### Update the backend's `ALLOWED_ORIGINS`

On the Oracle VM (`docs/deployment-oracle-cloud.md`): edit `.env`, set/extend `ALLOWED_ORIGINS` to include the deployed origin (e.g. `https://try-videolab.<account>.workers.dev`, plus any custom domain added later), then `docker compose up -d` to recreate the container with the new env var (editing `.env` alone doesn't affect an already-running container).

### Authorize the origin for Google Sign-In

In Google Cloud Console, add the deployed origin as an authorized JavaScript origin on the OAuth Client ID used for `VITE_GOOGLE_CLIENT_ID`/the backend's `GOOGLE_CLIENT_ID` (see `docs/authentication.md`). Without this, Google's sign-in flow itself rejects the request before it ever reaches the backend.

#### Acceptance criteria

- A full sign-in attempt from the deployed site succeeds end-to-end (Google popup → callback → session cookie set → landing on the app, not an error at any step).
- A cross-origin API call from the deployed frontend to the backend succeeds (no CORS error in the browser console) — confirms `ALLOWED_ORIGINS` actually took effect after the container recreate.

## (Optional) Custom domain

If a custom domain is wanted instead of `*.workers.dev`: project → **Settings → Domains & Routes → Add** (free, up to 100 per project). Cloudflare handles DNS/TLS automatically if the domain's nameservers are already on Cloudflare; otherwise it walks through a CNAME setup. If this is done, repeat the "close the loop" task above for the new domain as well — `ALLOWED_ORIGINS` and the OAuth origin both need the custom domain added (not just swapped), until/unless the `*.workers.dev` URL is fully retired.

## (Optional) Document the Wrangler CLI fallback

For one-off deploys without pushing to `main` (e.g. testing a local build before committing): `npm run build` locally, then `npx wrangler deploy` from `frontend/` (reads `wrangler.jsonc`, uploads `dist/` as static assets). Worth a short mention in `docs/web.md` or the root `README.md`'s deployment section once the project exists, alongside the Oracle Cloud doc — not required for the git-integration path above to work, just a documented escape hatch.
