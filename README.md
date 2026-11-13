# VidLife

Automated documentary video pipeline — given a domain, it researches a topic, writes a script, sources and animates assets, generates narration and music, and assembles a subtitled final video, in 19 steps.

The primary way to use it is the **web app**: sign in, start a run, watch it progress step by step, and review/edit/rerun any step from the browser. A CLI (`automate.py`) also exists for scripted/headless use — see [CLI](#cli-automatepy) below.

## Web App

Two local processes:

| Piece | What it is | Port |
|---|---|---|
| **Backend** | `backend/tasks.py` — FastAPI app exposing the pipeline as `/tasks/*` REST endpoints | `8081` |
| **Frontend** | React + Vite + TypeScript app | `5173` |

### 1. Start the backend

```bash
cd backend
pip install -r requirements.txt
python tasks.py
```

No API keys are required just to start the server — you configure them from the Settings page (step 3 below), or ahead of time by editing `settings.json` directly.

On every start, the backend also auto-migrates any leftover pre-multi-user `workspace/<domain>/<run_id>/` folders into the current per-user layout (`backend/workspace_migration.py`) — a no-op once nothing's left to migrate.

### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed URL (typically `http://localhost:5173`). The dev server proxies `/tasks/*` to the backend on `8081` — no CORS setup needed. Check `frontend/.env.local`: `VITE_MOCK_TASKS` should be `false` (the default) to talk to the real backend instead of mocked data.

### 3. Sign in

The app requires Google Sign-In, restricted to `@gmail.com` accounts (verified server-side — see [`docs/authentication.md`](docs/authentication.md)). Every route redirects to `/signin` until authenticated. Your workspace is scoped to your email's local-part, e.g. `jane.doe@gmail.com` → `workspace/jane.doe/`.

Add emails (one per line) to `admins.conf` at the project root to grant **admin** access — admins get a Settings nav link and can see/open every user's runs (via an `owner` query param), not just their own.

### 4. Configure API keys — Settings page (admins only)

Go to **Settings** in the nav bar. Fully data-driven from the backend (`GET/PUT /tasks/settings`), it lets you fill in:

- `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `RUNPOD_URL` — the providers the pipeline calls directly.
- `OPENROUTER_API_KEY` + `USE_OPENROUTER` — optional alternative AI backend, see [`docs/open-router.md`](docs/open-router.md).
- `GOOGLE_CLIENT_ID` — the OAuth Client ID the backend verifies sign-in tokens against.
- `MOCK_AI` — run the pipeline with mocked AI output, no API credits spent. Shows a site-wide amber banner when on.

Values are written to `settings.json` at the project root (gitignored).

### 5. Start a run — Generate page

The landing page (`/`) is the **Generate** flow: pick a domain and a video length/split, then **Generate Preview**. This always starts a fresh run and runs just step 1 (Research) for your approval — review the topic, **Try Different Topic** to reroll it, or **Approve & Open Pipeline** to kick off the rest and land on the run's detail page.

The **Pipeline** page's **New Run** button opens this exact same flow in a modal — there's only one implementation of it (`frontend/src/components/GenerateFlow.tsx`), so the two entry points never drift apart.

### 6. Monitor and manage runs — Pipeline page

**Pipeline** (`/tasks`) lists every run you own (or, for admins, every user's runs) as a card grid — domain, research topic, status (Active / Done / Failed / Partial), progress bar, video count. Active runs auto-refresh every 5s. Click a card to open its detail page (`/tasks/:domain/:runId`), which shows the topic at the top and has two panels:

- **Left — step timeline**: all 19 steps with status (done ✓ / failed ✗ / running spinner / pending). Steps beyond the reachable frontier are disabled until earlier ones finish.
- **Right — content panel**: the selected step's output, rendered with a viewer appropriate to its type (research sections, scene plan, asset manifest, image/video galleries, audio players, etc). Several viewers are editable and let you save corrections back before continuing.

Each step has a **Rerun** button to force a redo. There's also a **Wizard View** — a linear, one-step-at-a-time walkthrough of the same run, see [`docs/wizard-look.md`](docs/wizard-look.md).

### 7. Get the final video

Step 17 (Final Assembly) writes `output/final_video.mp4` inside that run's workspace (gitignored). Step 18 (Subtitles) then generates `subtitle.md` — reviewable/editable per-scene captions with timing — from the narration's timing (ElevenLabs character-level alignment when available, falling back to a coarser pause-based heuristic otherwise) and burns those captions into `final_video.mp4` in place. Preview and download the (now subtitled) video from step 17's entry in the content panel; review or correct the captions themselves from step 18's entry.

### Troubleshooting

- **Pipeline page shows mocked/stale data** — check `VITE_MOCK_TASKS=false` in `frontend/.env.local` and restart `npm run dev`.
- **A step fails with a "missing API key" message** — fill in the key on the Settings page, or toggle `MOCK_AI` on for dev testing without real keys.
- **Hard refresh on a `/tasks/...` URL shows `{"detail":"Not Found"}`** — the dev proxy's `/tasks` route allowlist in `frontend/vite.config.ts` only forwards real backend sub-paths (`runs`, `auth`, `settings`, `files`, `estimate-cost`); everything else falls through to the SPA. Restart `npm run dev` if you've just pulled this fix.
- **Nothing loads / network errors on the Pipeline page** — confirm `backend/tasks.py` is running on port `8081`.

## The Pipeline (19 Steps)

Each run executes: Research → Story Script → Scene Breakdown → Asset Manifest → Asset Acquisition → Fetch Assets → AI Asset Generation → Animation Prompt → Video Animation → Narration Script → Narration Audio → Music Prompt → Music Audio → Asset Inventory → Narration Timing → Edit Decision List → Final Assembly → Subtitles → Platform Metadata.

See [`docs/pipeline-overview.md`](docs/pipeline-overview.md) for the full flow diagram and key decisions, and the per-area docs below for implementation detail.

## Domains

`political` · `general_knowledge` · `science` · `business` · `history` · `sports` · `technology` · `general`

Each domain has its own prompt files under `prompts/{domain}/` and a dedicated ElevenLabs voice.

## CLI (`automate.py`)

A scripted, non-web way to run the same pipeline against the legacy `workspace/{domain}/{run_id}/` layout (not the web app's per-user workspaces) — useful for headless/batch runs.

```bash
pip install google-genai requests moviepy matplotlib
brew install ffmpeg
source .keys   # copy .keys from template and fill in your values

python automate.py                                      # full run — resumes latest workspace
python automate.py --new                                # full run — always starts a fresh workspace
python automate.py --step 3 --workspace 200619          # run step 3 (skip if already done)
python automate.py --step 3 --workspace 200619 --new    # force re-run step 3
python automate.py --status --workspace 200619          # show step status table for a workspace
```

`--workspace` is required with `--step`/`--status` (the time portion of the folder name, e.g. `200619` from `2026-06-12_200619`). `--step` skips the step if output already exists — pass `--new` to force re-run.

## Testing

```bash
# Backend
cd backend && python -m pytest

# Frontend
cd frontend && npx tsc --noEmit -p . && npm run build
```

## API Keys

| Key | Service | Where it's set |
|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio / Vertex AI | Settings page or `settings.json` (web), `.keys` (CLI) |
| `ELEVENLABS_API_KEY` | ElevenLabs (TTS + music) | same |
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` | Stock asset fetch | same |
| `RUNPOD_URL` | Self-hosted RunPod video-animation server | same |
| `OPENROUTER_API_KEY` | Optional alternative AI backend | same |
| `GOOGLE_CLIENT_ID` | OAuth audience for sign-in verification | `settings.json` / `VITE_GOOGLE_CLIENT_ID` |

## Documentation

| Doc | Contents |
|-----|----------|
| [Web App](docs/web.md) | Step-by-step guide to running the web app (superseded in parts by this README — kept for the original planning detail) |
| [Authentication](docs/authentication.md) | Google Sign-In, per-user workspaces, admin gating — design decisions |
| [Tasks API](docs/tasks-api.md) | Full REST reference for `backend/tasks.py`'s `/tasks/*` endpoints |
| [Wizard View](docs/wizard-look.md) | The linear, one-step-at-a-time run view |
| [Pipeline Overview](docs/pipeline-overview.md) | `automate.py`'s 18-step CLI flow diagram, key decisions, execution order (the web app's pipeline adds a 19th step, Subtitles — see [Tasks API](docs/tasks-api.md)) |
| [Scaffolding](docs/scaffolding.md) | CLI args, workspace layout, state file, domain/voice config |
| [LLM Steps](docs/llm-steps.md) | Gemini runner, text-generation steps (1–5, 8, 10, 12, 16, 19) |
| [Asset Generation](docs/asset-generation.md) | Steps 6–9: fetch, Imagen 4, animation prompts, RunPod |
| [Audio Generation](docs/audio-generation.md) | Step 11 ElevenLabs TTS (+ character-level alignment), Step 13 music generation |
| [Assembly](docs/assembly.md) | Step 17 — ffmpeg assembly via `assemble.py`; Step 18 — subtitle generation and burn-in; Step 19 — platform metadata |
| [OpenRouter](docs/open-router.md) | Using OpenRouter as a switchable alternative AI provider |
| [RunPod Setup](docs/runpod-setup.md) | Setting up the self-hosted video-animation server for step 9 |

## Project Structure

```
backend/                 # FastAPI app — the web app's pipeline API
  tasks.py                 # /tasks/* endpoints: runs, steps, settings passthrough, file serving
  auth.py                  # Google Sign-In verification, sessions
  settings.py               # settings.json read/write, admin-gated
  workspace_migration.py   # moves pre-multi-user workspaces under a user folder (runs on every boot)
  subtitles.py             # step 18's chunking/parsing logic (alignment + pause-heuristic paths, subtitle.md format)
  tests/                   # pytest suite
frontend/                # React + Vite + TypeScript web app
  src/pages/                # GeneratePage, TasksListPage, RunDetailPage, RunWizardPage, SettingsPage, SignInPage
  src/components/           # GenerateFlow (shared by Generate page + New Run modal), viewers, UI primitives
  src/api/tasks.ts          # Typed client for /tasks/*
server/                  # standalone GPU-bound Wan 2.2 I2V inference server (separate from the pipeline; see server/README.md)
automate.py              # CLI pipeline runner (legacy workspace layout)
pipeline.py              # original manual pipeline (reference)
scripts/                 # one-off maintenance scripts (e.g. workspace migration CLI) and shared pipeline scripts
  assemble.py               # step 17 — ffmpeg/moviepy assembly
  generate_subtitles.py    # step 18 — subtitle.md + burned-in captions
  text_overlay.py          # shared Pillow/MoviePy text-overlay rendering (steps 17 and 18)
fonts/                   # NotoSansDevanagari-Bold.ttf (SIL OFL) used for all burned-in text/captions
prompts/
  {domain}/
    01_research.md
    02_story.md
    02b_platform_metadata.md   # step 19 — YouTube title, description, hashtags, tags (runs last)
    03_scene_breakdown.md
    04_asset_planning.md
    05_asset_acquisition.md
    08_animation_prompt.md     # step 8 — per-asset animation description for RunPod
    10_narration.md
    12_music.md
    16_creative_director.md
docs/                    # documentation (see table above)
admins.conf              # admin allowlist for the web app (one Gmail address per line)
settings.json            # web app API keys/config — gitignored, never commit
.keys                    # CLI API keys — gitignored, never commit
workspace/               # generated workspaces — gitignored
output/                  # final videos (CLI path) — gitignored
```
