# Tasks API — Pipeline Runner Endpoints

Expose the VidLife pipeline (`automate.py` logic) as FastAPI endpoints in `backend/tasks.py`.
`automate.py` is **not imported or modified** — all step runners are reimplemented independently.

The router is mounted at `/tasks` inside `backend/server.py`.

## Key decisions

| Concern | Decision |
|---|---|
| Isolation | `tasks.py` is fully independent — no import from `automate.py` |
| Execution | Background threads (same pattern as `backend/server.py` job handling) |
| Run identity | Workspace folder name (e.g. `2026-08-20_143022`) is the run ID |
| Domain | Passed as a request parameter (no interactive menu) |
| API keys | Env vars at startup (`GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `RUNPOD_URL`) |
| Mounting | FastAPI router at `/tasks` included in `backend/server.py` |
| Source of truth | Filesystem (`workspace/{domain}/{run_id}/pipeline_state.json`) |
| Active tracking | In-memory dict for runs currently executing (step ID + status) |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/tasks/runs` | Start a full run (resume or fresh) |
| `POST` | `/tasks/runs/{domain}/{run_id}/steps/{step_id}` | Run/rerun a single step |
| `GET` | `/tasks/runs/{domain}/{run_id}` | Status of a specific run |
| `GET` | `/tasks/runs` | List all workspaces + videos across all domains |

---

## Create `backend/tasks.py`

### Constants and config

- STEPS list (same 18-step definitions as automate.py)
- DOMAIN_VOICE_MAP
- BURN_KEY_PREFIXES
- Model name constants (Gemini, Imagen, ElevenLabs)
- Env var reads (GEMINI_API_KEY, ELEVENLABS_API_KEY, PEXELS_API_KEY, RUNPOD_URL)
- Path constants (BASE_DIR points two levels up to project root, WORKSPACE_ROOT, PROMPTS_DIR, SCRIPTS_DIR)

### Active run tracking

In-memory dict `_active_runs: dict[str, dict]` keyed by `"{domain}/{run_id}"`.
Each entry: `{ "step_id": str | None, "status": "running" | "idle" | "done" | "failed" }`.
Protected by a threading.Lock.

### Workspace helpers

- `new_workspace(domain)` → creates `workspace/{domain}/YYYY-MM-DD_HHMMSS/`, returns (run_id, path)
- `latest_workspace(domain)` → finds most recent workspace for domain
- `find_workspace(domain, run_id)` → finds workspace by exact folder name
- `load_state(ws)` / `save_state(ws, state)` → read/write `pipeline_state.json`

### Prompt resolver

`resolve_prompt_file(step_id, domain, prompt_file=None)` → finds prompt file in `prompts/{domain}/`

### Step runners (reimplemented independently)

Each runner has signature `(step, ws, state, **kwargs)`:

- `run_gemini_step` — reads prompt file, fills `{{var}}` placeholders, calls Gemini API, saves output
- `run_fetch_assets` — parses `asset_acquisition.md`, writes spec files per asset
- `run_imagen_generation` — web-fetch pass (search_query.txt → Wikipedia/Wikimedia/Pexels) + Imagen pass (generated.txt → Imagen 4)
- `run_animation_prompt_step` — Gemini generates `animated.txt` per static asset
- `run_runpod_animation` — submits to RunPod server, polls status, downloads `animated.mp4`
- `run_elevenlabs_tts` — ElevenLabs TTS → `narration.mp3`
- `run_elevenlabs_music` — ElevenLabs sound gen → `music.wav`, ffmpeg loop to 210s
- `run_script` — subprocess call to `scripts/{script}` with WORKSPACE_DIR env var

### Pipeline execution

- `output_exists(step, ws)` → checks if step output already exists on disk
- `dispatch(step, ws, state, clean=False)` → routes to correct runner by step type
- `execute_step(step, ws, state, force=False, clean=False)` → runs step, updates state, saves

### FastAPI router

`router = APIRouter(prefix="/tasks", tags=["tasks"])`

#### `POST /tasks/runs`

Body: `{ domain: str, fresh: bool = False }`

- Validates domain
- If `fresh=True`: creates new workspace, initialises state
- If `fresh=False`: resumes latest workspace (creates new one if none exists)
- Spawns background thread running all steps sequentially
- Thread updates `_active_runs` on step transitions and completion
- Returns: `{ run_id, domain, workspace, fresh, message }`

#### `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}`

Body: `{ force: bool = False }`

- Validates domain, resolves workspace by run_id, validates step_id
- Spawns background thread running that single step (with force flag)
- Returns: `{ run_id, domain, step_id, force, message }`

#### `GET /tasks/runs/{domain}/{run_id}`

- Resolves workspace, loads `pipeline_state.json`
- Checks `_active_runs` for current in-progress step
- Returns per-step status (done / failed / pending) and active step info

#### `GET /tasks/runs`

- Walks `workspace/` directory, collects all `{domain}/{run_id}` pairs
- For each: loads pipeline_state.json, lists all `animated.mp4` files
- Returns array sorted by run_id descending (newest first)

---

## Update `backend/server.py`

Add after existing imports:
```python
from tasks import router as tasks_router
app.include_router(tasks_router)
```

---

## Create `docs/tasks-api.md`

Full API reference with request/response schemas and curl examples for all 4 endpoints.
