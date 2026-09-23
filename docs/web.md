# Web UI: Generating Videos via the Pipeline Runner

This is the web-based alternative to the CLI pipeline (`python automate.py`, documented in the root [`README.md`](../README.md)). It runs the exact same 18-step documentary pipeline, but you drive it from a browser — starting runs, watching step-by-step progress, inspecting/editing intermediate output, and rerunning individual steps — instead of a terminal.

> This doc does **not** cover `server/server.py` (the standalone GPU-bound Wan 2.2 image-to-video inference server meant for RunPod). See [`server/README.md`](../server/README.md) for that. It also doesn't repeat the raw REST API reference — see [`docs/tasks-api.md`](./tasks-api.md) for that, and [`docs/pipeline-overview.md`](./pipeline-overview.md) for the 18-step architecture.

## Architecture

Two processes, both run locally:

| Piece | What it is | Port | Started from |
|---|---|---|---|
| **Backend** | `backend/tasks.py` — FastAPI app exposing the pipeline as `/tasks/*` REST endpoints | `8081` | `backend/` directory |
| **Frontend** | React + Vite app | `5173` (Vite dev default) | `frontend/` directory |

The frontend's dev server proxies `/tasks/*` requests to `http://localhost:8081` (see `frontend/vite.config.ts`), so you don't need to configure CORS or hit the backend directly — just open the Vite dev URL in your browser.

(The frontend also proxies `/api/*` to `http://localhost:8080` for the separate, unrelated Wan I2V server — irrelevant here, and mocked by default via `VITE_MOCK=true`.)

## 1. Start the backend

```bash
cd backend
pip install -r requirements.txt
python tasks.py
```

This starts `backend/tasks.py` on `http://localhost:8081`. Run it from inside `backend/` — its internal imports (`mocks/`, `open_router/`) resolve relative to that working directory.

No API keys are required just to start the server. You'll configure them from the Settings page in step 3 (or beforehand by creating `settings.json` — see below).

## 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed URL (typically `http://localhost:5173`).

Check `frontend/.env.local`:

```
VITE_MOCK_TASKS=false
```

This must be `false` (the default) for the Pipeline tab to talk to the real `backend/tasks.py` instead of mocked data. `VITE_MOCK=true` can stay as-is — it only affects the unrelated `/api` (Wan I2V) mock and doesn't impact the pipeline.

## 3. Configure API keys — Settings page

Go to **Settings** (`/settings`) in the nav bar. This page is fully data-driven from the backend (`GET /tasks/settings`) and lets you fill in:

- `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `RUNPOD_URL` — the self-hosted/direct providers (same keys as the CLI's `.keys` file).
- `OPENROUTER_API_KEY` + `USE_OPENROUTER` — optional alternative AI backend (see [`docs/open-router.md`](./open-router.md)).
- `MOCK_AI` — toggle to run the pipeline with mocked AI output for dev/testing without spending API credits. When on, a site-wide amber "AI Mock Mode is ON" banner appears.

Click **Save**. Values are written to `settings.json` at the project root (`PUT /tasks/settings`) — this is separate from the CLI's `.keys` file. If you're only using the web UI, you don't need `.keys` at all; if you use both the CLI and the web UI, you'll need to keep both in sync manually.

## 4. Start a pipeline run — Generate page

Go to **Generate** (`/`, the default landing page). Pick a domain (`political`, `general_knowledge`, `science`, `business`, `history`, `sports`, `technology`, `general`), then choose a mode:

- **Fresh start** — creates a new workspace. First runs only step 1 (Research) and shows you the generated research topic/content for review before continuing. From there you can:
  - **Try Different Topic** — reruns step 1 to get a different research angle.
  - **Cancel** — deletes the workspace.
  - **Approve & Continue** — kicks off the remaining steps and takes you to the run's detail page.
- **Resume latest** — continues the most recent workspace for that domain, skipping steps already completed, and takes you straight to the run's detail page.

You can also start a run from the **Pipeline** tab (see below) via its "New Run" button, which offers the same fresh/resume choice without the topic-preview step.

## 5. Monitor and manage runs — Pipeline tab

Go to **Pipeline** (`/tasks`) to see every run across all domains as a card grid: domain, status (Active / Done / Failed / Partial), progress bar, and video count. Cards for active runs auto-refresh every 5 seconds. Click a card (or start a new run) to open the run detail page (`/tasks/:domain/:run_id`).

The run detail page has two panels:

- **Left — step timeline**: all steps with a status indicator (done ✓ / failed ✗ / running spinner / pending step number). Click any step to view it.
- **Right — content panel**: the selected step's output, rendered with a viewer appropriate to its content type (plain text, research sections, scene plan, asset manifest, generated image gallery, etc.). Some viewers (research, scene plan, asset plan) are editable and let you save corrections back via `PUT` before continuing.

Each step has a **Rerun** button to force it to run again (equivalent to the CLI's per-step force-rerun, or `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}` with `{"force": true}`). While the run is active, the page polls every 3 seconds and auto-selects whichever step is currently running.

## 6. Get the final video

The pipeline writes into `workspace/{domain}/{run_id}/` for intermediate assets, and the final rendered video to `output/final_video.mp4` inside that same run's workspace (step 17, Final Assembly) — both are gitignored, same as the CLI path. You can preview/download it from the run's step 17 entry in the content panel, or grab the file directly from disk.

## Troubleshooting

- **Pipeline tab shows mocked/stale data** — check `VITE_MOCK_TASKS=false` in `frontend/.env.local` and restart `npm run dev`.
- **A step fails immediately with a "missing API key" message** — fill in the corresponding key on the Settings page (or toggle `MOCK_AI` on for dev testing without real keys).
- **Nothing loads / network errors in the Pipeline tab** — confirm `backend/tasks.py` is actually running on port `8081` (`cd backend && python tasks.py`).
