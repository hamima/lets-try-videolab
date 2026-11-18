# Deploy the Frontend to Cloudflare Pages (Free Plan)

The frontend (`frontend/`) is a static Vite + React SPA — `npm run build` already produces a plain `dist/` folder with no server-side rendering or API routes of its own (all `/tasks/*` and `/api/*` calls go to the separately-deployed backend, see `docs/deployment-oracle-cloud.md`). Cloudflare Pages is a pure static-asset host plus optional "Functions" for dynamic routes; since this app has none, the free plan's Pages Functions limits (100k requests/day, 10ms CPU/request) never come into play — only the static-hosting limits matter, which are generous and verified current as of Cloudflare's docs (last modified 2026-09-05): 500 builds/month (20-minute timeout), **unlimited bandwidth**, 100 custom domains/project, 20,000 files/site (25MiB max per file) — all comfortably enough for this app's single-page bundle.

This repo is a **monorepo** (`frontend/`, `backend/`, `scripts/`, etc. all siblings at the root) — Cloudflare Pages needs an explicit **root directory** setting for this, and it's the single most commonly-missed step (tucked under "Advanced settings" in the dashboard): miss it, and Pages builds from the repo root instead, which has no `package.json`/`index.html` at all, or silently serves the wrong thing. This plan calls it out explicitly as its own task rather than folding it into generic setup.

**Key decisions:**

- **Git integration (GitHub), not CLI-only deploys.** Connects directly to this repo's GitHub remote (`git@github.com:hamima/lets-try-videolab.git`) — every push to `main` triggers an automatic build/deploy, matching the git-push-driven workflow already used for the backend (Oracle VM: `git pull && docker compose up -d --build`). Manual `wrangler pages deploy` stays available as a documented fallback (last task) for one-off deploys without pushing, but isn't the primary path.
- **Root directory: `frontend`.** Build command `npm run build` (already `tsc -b && vite build` per `package.json`), output directory `dist` — both relative to the root directory, not the repo root.
- **Build output directory is configured via `frontend/wrangler.jsonc`, not a dashboard field.** Cloudflare merged the classic Pages Git-integration dashboard into a unified "Workers Builds" flow (confirmed as of ~Oct 2026) — that dashboard has a "Deploy command" field but no "Build output directory" field at all. `wrangler.jsonc`'s `pages_build_output_dir` key is now the source of truth for this instead; once it's set, Cloudflare deploys the built static assets automatically right after the build, so **the dashboard's Deploy command field should be left empty** (it's for Worker-style projects that need an explicit `wrangler deploy` step, which a plain static SPA doesn't).
- **Node version is pinned explicitly**, not left to Cloudflare's build-image default (which may be older than this project's Vite 8 / TypeScript toolchain expects) — via a committed `.node-version` file, which Cloudflare's build system auto-detects.
- **`VITE_API_URL` and `VITE_GOOGLE_CLIENT_ID` are set as Cloudflare dashboard environment variables, not committed into `frontend/.env.production`.** Both are deployment-specific (the backend's actual public URL, an OAuth Client ID tied to this exact origin) — `.env.production`'s existing placeholders for these stay commented out/empty, consistent with how that file already documents them as "fill in per deployment." `VITE_MOCK`/`VITE_MOCK_TASKS=false` already live in the committed `.env.production` and need no dashboard override.
- **SPA routing needs no new work** — `frontend/public/_redirects` (`/* /index.html 200`) already exists from the earlier Render/Netlify-style fix, and Cloudflare Pages reads the exact same `_redirects` syntax (confirmed via Cloudflare's own Netlify-migration docs). Cloudflare also auto-detects SPAs and falls back to `index.html` even without this file when no top-level `404.html` exists, so this is a belt-and-suspenders verification task, not new work.
- **This plan ends with a "close the loop" task**, not left implicit: once Cloudflare assigns the real `*.pages.dev` (or custom domain) URL, two things elsewhere need updating to actually work together — the backend's `ALLOWED_ORIGINS` (Oracle VM's `.env`, needs a container recreate) and the Google OAuth Client ID's authorized JavaScript origins (Google Cloud Console) — both already documented as prerequisites in `docs/authentication.md`/`docs/deployment-oracle-cloud.md`, but easy to forget once the frontend itself is "deployed."

## Create and configure the Cloudflare Pages project

### Connect the repo

In the Cloudflare dashboard: **Workers & Pages → Create → Pages → Connect to Git**. Authorize/select the `hamima/lets-try-videolab` GitHub repo, branch `main`.

### Set the monorepo root directory and build settings

Under **Advanced settings** (or the build-config step during initial setup) in the Workers Builds dashboard:

- **Root directory**: `frontend`
- **Build command**: `npm run build`
- **Deploy command**: leave **empty** — see the "Key decisions" note above. Once `frontend/wrangler.jsonc` (next step) is in place with `pages_build_output_dir` set, Cloudflare recognizes this as a Pages-style project and deploys automatically after the build runs; setting a deploy command here is only for Worker-style projects that run their own `wrangler deploy`.
- Framework preset: select **Vite** if offered — it pre-fills the build command, but the root directory still has to be set explicitly regardless of preset (the preset doesn't know this is a monorepo).

### Add `frontend/wrangler.jsonc`

```jsonc
{
  "name": "vidlife",                 // must match the Cloudflare project's name exactly
  "pages_build_output_dir": "dist",  // relative to frontend/, matches vite build's output
  "compatibility_date": "2026-11-18"
}
```

This is the file that replaces the dashboard's old "Build output directory" field. `name` must exactly match whatever the project was named when it was created in the Cloudflare dashboard.

#### Acceptance criteria

- The first build actually runs `npm run build` inside `frontend/` (visible in the build log's working directory), not the repo root.
- The build succeeds, and Cloudflare deploys automatically right after — no separate "deploy" step appears in the log, confirming `pages_build_output_dir` was picked up and the project is being treated as Pages-style, not Worker-style.
- The deployed site actually renders the app (not a 404 or the raw repo README) — confirms the root directory took effect too, not just that a build happened.

### Pin the Node version

Add `frontend/.node-version` containing the Node major version this project is developed against (matching `frontend/package.json`'s toolchain — no `engines` field exists yet to cross-check against, so use whatever version `nvm current`/`node --version` reports in the active dev environment). Cloudflare's build image auto-detects this file and uses the matching Node version instead of its own default.

#### Acceptance criteria

- The build log shows the pinned Node version being used, not a mismatched default.

## Configure environment variables

In **Settings → Environment variables** for the Pages project, for the **Production** environment (and **Preview**, if preview deploys on branches/PRs are desired against the same backend):

- `VITE_API_URL` — the backend's real public HTTPS URL (from `docs/deployment-oracle-cloud.md`'s TLS setup — Cloudflare Tunnel or Caddy, whichever was chosen there). Must be `https://`, not `http://` — a `https://` Pages site calling a plain `http://` backend gets blocked as mixed content by the browser regardless of CORS config.
- `VITE_GOOGLE_CLIENT_ID` — only needed here if it differs from `frontend/.env.production`'s committed default (it won't have one, since that file leaves it as a placeholder) — otherwise sign-in fails with the same "not configured" error `SignInPage.tsx` already surfaces gracefully.

Trigger a rebuild after setting these (Cloudflare env var changes don't retroactively apply to already-built deploys) — either push an empty commit or use the dashboard's "Retry deployment."

#### Acceptance criteria

- `GET`-ing the deployed site and opening the browser's network tab shows API calls going to the configured `VITE_API_URL`, not a relative `/tasks` path 404ing against Cloudflare's own static host.
- Changing either dashboard env var and retriggering a build actually changes the resulting bundle's behavior (confirms they're truly build-time, matching the existing `VITE_API_URL` documentation in the root `README.md`).

## Verify SPA routing and the first real deploy

### Confirm `_redirects` is picked up and deep-link routes work

After the first successful deploy, directly load (not navigate from the homepage) a deep client-side route — e.g. `https://<project>.pages.dev/tasks` or `/tasks/<domain>/<run-id>` — both as a hard URL load and as a page refresh once already on it. This is exactly the class of bug already fixed once for the Vite dev proxy (`/tasks/*` 404ing on hard refresh) and for Netlify-style static hosts (`frontend/public/_redirects`) — confirm the fix actually carries over to Cloudflare specifically rather than assuming it does because the syntax matches.

#### Acceptance criteria

- A hard-loaded `/tasks` URL (no prior client-side navigation) renders the app, not Cloudflare's default 404 page.
- A browser refresh while on `/tasks/<domain>/<run-id>` also renders correctly.

## Close the loop — wire the real deployed URLs together

Two things elsewhere in the stack need the Pages project's actual URL before the deployed frontend can fully work, not just load:

### Update the backend's `ALLOWED_ORIGINS`

On the Oracle VM (`docs/deployment-oracle-cloud.md`): edit `.env`, set/extend `ALLOWED_ORIGINS` to include the Pages URL (e.g. `https://vidlife.pages.dev`, plus any custom domain added later), then `docker compose up -d` to recreate the container with the new env var (editing `.env` alone doesn't affect an already-running container).

### Authorize the origin for Google Sign-In

In Google Cloud Console, add the Pages URL as an authorized JavaScript origin on the OAuth Client ID used for `VITE_GOOGLE_CLIENT_ID`/the backend's `GOOGLE_CLIENT_ID` (see `docs/authentication.md`). Without this, Google's sign-in flow itself rejects the request before it ever reaches the backend.

#### Acceptance criteria

- A full sign-in attempt from the deployed Pages URL succeeds end-to-end (Google popup → callback → session cookie set → landing on the app, not an error at any step).
- A cross-origin API call from the deployed frontend to the backend succeeds (no CORS error in the browser console) — confirms `ALLOWED_ORIGINS` actually took effect after the container recreate.

## (Optional) Custom domain

If a custom domain is wanted instead of `*.pages.dev`: **Pages project → Custom domains → Add** (free, up to 100 per project). Cloudflare handles DNS/TLS automatically if the domain's nameservers are already on Cloudflare; otherwise it walks through a CNAME setup. If this is done, repeat the "close the loop" task above for the new domain as well — `ALLOWED_ORIGINS` and the OAuth origin both need the custom domain added (not just swapped), until/unless the `*.pages.dev` URL is fully retired.

## (Optional) Document the Wrangler CLI fallback

For one-off deploys without pushing to `main` (e.g. testing a local build before committing): `npx wrangler pages deploy frontend/dist --project-name=<project>`, after running `npm run build` locally first. Worth a short mention in `docs/web.md` or the root `README.md`'s deployment section once the Pages project exists, alongside the Oracle Cloud doc — not required for the git-integration path above to work, just a documented escape hatch.
