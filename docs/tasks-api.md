# Tasks API Reference

The Tasks API exposes the VidLife pipeline as HTTP endpoints, allowing callers to start runs,
rerun individual steps, check status, and list all generated videos — without using the CLI.

Base URL (local dev): `http://localhost:8080`

All task endpoints are mounted at `/tasks`.

---

## Supported domains

`political` · `general_knowledge` · `science` · `business` · `history` · `sports` · `technology` · `general`

## Step IDs

| ID | Name | Type |
|---|---|---|
| `1` | Research | gemini |
| `2` | Story Script | gemini |
| `3` | Scene Breakdown | gemini |
| `4` | Asset Manifest | gemini |
| `5` | Asset Acquisition Instructions | gemini |
| `6` | Fetch Assets | fetch_assets |
| `7` | AI Image Generation | imagen |
| `8` | Animation Prompt | animation_prompt |
| `9` | Video Animation | runpod_animation |
| `10` | Narration Script | gemini |
| `11` | Narration Audio | tts |
| `12` | Music Prompt | gemini |
| `13` | Music Audio | music |
| `14` | Asset Inventory | script |
| `15` | Narration Timing | script |
| `16` | Edit Decision List | gemini |
| `17` | Final Assembly | script |
| `18` | Platform Metadata | gemini |

---

## `POST /tasks/runs`

Create or resume a workspace for a domain. Resumes the latest workspace by default; pass `fresh: true` to start from scratch.

**Full pipeline auto-run is gated behind the `ENABLE_FULL_PIPELINE` config flag (default `false`).** When the flag is off:

- A plain `fresh`/resume request (`preview_only` not set) just creates/resumes the workspace and returns immediately — **no background run is dispatched**. Use `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}` to run each of the 18 steps individually.
- A fresh-start **preview** request (`fresh: true` **and** `preview_only: true`) still runs — this is the only path that auto-executes in the background regardless of the flag. It runs step 1 only, then stops and waits for approval (see "Preview flow" below).

When `ENABLE_FULL_PIPELINE=true`, non-preview requests behave as before: the full 18-step pipeline is dispatched in a background thread immediately.

### Request body

```json
{
  "domain": "political",
  "fresh": false,
  "preview_only": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | One of the supported domains |
| `fresh` | boolean | no (default `false`) | `true` = create new workspace; `false` = resume latest |
| `preview_only` | boolean | no (default `false`) | `true` (with `fresh: true`) = run step 1 only and wait for approval, ignoring `ENABLE_FULL_PIPELINE` |

### Response `200` — `ENABLE_FULL_PIPELINE=false`, non-preview request

```json
{
  "run_id": "2026-08-20_143022",
  "domain": "political",
  "workspace": "workspace/political/2026-08-20_143022",
  "fresh": false,
  "preview_only": false,
  "message": "Workspace ready — run steps individually"
}
```

### Response `200` — preview request (`fresh: true`, `preview_only: true`)

```json
{
  "run_id": "2026-08-20_143022",
  "domain": "political",
  "workspace": "workspace/political/2026-08-20_143022",
  "fresh": true,
  "preview_only": true,
  "message": "Preview started — awaiting approval after step 1"
}
```

### Response `200` — `ENABLE_FULL_PIPELINE=true`, non-preview request

```json
{
  "run_id": "2026-08-20_143022",
  "domain": "political",
  "workspace": "workspace/political/2026-08-20_143022",
  "fresh": false,
  "preview_only": false,
  "message": "Full run started"
}
```

### Example

```bash
curl -X POST http://localhost:8080/tasks/runs \
  -H "Content-Type: application/json" \
  -d '{"domain": "political", "fresh": false}'
```

---

## `POST /tasks/runs/{domain}/{run_id}/continue`

Resume the full pipeline after a preview approval — runs all remaining steps in the background.

**Gated behind `ENABLE_FULL_PIPELINE`** (default `false`). When the flag is off, this endpoint always returns `409`. The endpoint is kept functional (not removed) for future re-enablement; when the flag is on, behavior is unchanged from before — it dispatches `_run_full_pipeline` in a background thread.

### Response `200` (flag on)

```json
{ "run_id": "2026-08-20_143022", "domain": "political", "message": "Pipeline resumed" }
```

### Response `409` (flag off, the default)

```json
{ "detail": "Full pipeline run is disabled" }
```

### Example

```bash
curl -X POST http://localhost:8080/tasks/runs/political/2026-08-20_143022/continue
```

---

## `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}`

Run or rerun a single pipeline step in an existing workspace.

Pass `force: true` to rerun even if the step output already exists.

### Path parameters

| Parameter | Description |
|---|---|
| `domain` | Domain of the workspace |
| `run_id` | Workspace folder name (e.g. `2026-08-20_143022`) |
| `step_id` | Step ID to execute (e.g. `3`, `7`, `11`) |

### Request body

```json
{
  "force": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `force` | boolean | no (default `false`) | `true` = rerun even if output exists |

### Response `200`

```json
{
  "run_id": "2026-08-20_143022",
  "domain": "political",
  "step_id": "3",
  "force": false,
  "message": "Step queued"
}
```

### Example — run step 3

```bash
curl -X POST \
  http://localhost:8080/tasks/runs/political/2026-08-20_143022/steps/3 \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

### Example — force rerun step 7 (re-generates all images)

```bash
curl -X POST \
  http://localhost:8080/tasks/runs/political/2026-08-20_143022/steps/7 \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

---

## `POST /tasks/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/animate`

Animate (or re-animate) a single Step 9 asset, synchronously. This is the per-asset counterpart to
the batch step 9 run — the frontend's "Animate" / "Re-animate" button calls this endpoint directly
instead of rerunning the whole step.

If `animated.mp4` already exists for the asset it is deleted first, then regenerated unconditionally
(there's no "skip if exists" behavior here, unlike the batch step run).

### Path parameters

| Parameter | Description |
|---|---|
| `domain` | Domain of the workspace |
| `run_id` | Workspace folder name |
| `scene_id` | Scene number (e.g. `1`), matches the `assets/scene_{scene_id}/` folder |
| `asset_id` | Asset number within the scene (e.g. `1`), matches `asset_{asset_id}/` |

### Response `200`

```json
{ "url": "/tasks/files/political/2026-08-20_143022/assets/scene_1/asset_1/animated.mp4" }
```

### Errors

| Status | When |
|---|---|
| `400` | Unknown domain, or no `animated.txt` prompt file found for this asset |
| `404` | Workspace or asset directory not found |
| `422` | Animation generation failed (backend/API error) |

### Example

```bash
curl -X POST \
  http://localhost:8080/tasks/runs/political/2026-08-20_143022/assets/1/1/animate
```

---

## `GET /tasks/runs/{domain}/{run_id}`

Get the full status of a specific pipeline run, including per-step status and any currently active step.

### Path parameters

| Parameter | Description |
|---|---|
| `domain` | Domain of the workspace |
| `run_id` | Workspace folder name |

### Response `200`

```json
{
  "run_id": "2026-08-20_143022",
  "domain": "political",
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "workspace": "workspace/political/2026-08-20_143022",
  "active": true,
  "active_step": "3",
  "steps": [
    { "id": "1", "name": "Research",        "type": "gemini",  "status": "done"    },
    { "id": "2", "name": "Story Script",    "type": "gemini",  "status": "done"    },
    { "id": "3", "name": "Scene Breakdown", "type": "gemini",  "status": "running" },
    { "id": "4", "name": "Asset Manifest",  "type": "gemini",  "status": "pending" }
  ]
}
```

Step `status` values: `done` · `failed` · `running` · `pending`

### Example

```bash
curl http://localhost:8080/tasks/runs/political/2026-08-20_143022
```

---

## `GET /tasks/runs`

List all workspaces across all domains, with step completion summary and generated video files.

### Query parameters

| Parameter | Type | Description |
|---|---|---|
| `domain` | string (optional) | Filter by domain |

### Response `200`

```json
[
  {
    "domain": "political",
    "run_id": "2026-08-20_143022",
    "workspace": "workspace/political/2026-08-20_143022",
    "created_at": "2026-08-20T14:30:22",
    "active": false,
    "steps_completed": 12,
    "steps_failed": 1,
    "steps_total": 18,
    "videos": [
      "workspace/political/2026-08-20_143022/assets/scene_1/asset_1/animated.mp4",
      "workspace/political/2026-08-20_143022/assets/scene_2/asset_1/animated.mp4"
    ]
  }
]
```

Results are sorted newest first.

### Example — list all

```bash
curl http://localhost:8080/tasks/runs
```

### Example — filter by domain

```bash
curl "http://localhost:8080/tasks/runs?domain=political"
```

---

## Error responses

| Status | When |
|---|---|
| `400` | Invalid domain or step ID |
| `404` | Workspace or run_id not found |
| `409` | A run is already active for this workspace, or `/continue` was called while `ENABLE_FULL_PIPELINE=false` |
| `422` | Per-asset animation request failed (see `/assets/{scene_id}/{asset_id}/animate`) |

```json
{ "detail": "No workspace found for run_id '2026-08-20_143022' in domain 'political'" }
```

---

## Environment variables required

| Variable | Used by |
|---|---|
| `GEMINI_API_KEY` | Steps 1–5, 8, 10, 12, 16, 18 |
| `ELEVENLABS_API_KEY` | Steps 11, 13 |
| `PEXELS_API_KEY` | Step 7 (Pexels fallback) |
| `RUNPOD_URL` | Step 9 (animation server) |

Set these via `source .keys` before starting the backend.

---

## Settings flags

In addition to environment variables, some behavior is controlled via `settings.json`
(`backend/settings.py`'s `SETTINGS_KEYS`), editable through the settings UI/API:

| Key | Type | Default | Effect |
|---|---|---|---|
| `ENABLE_FULL_PIPELINE` | bool | `false` | When `false`, `POST /tasks/runs` no longer auto-dispatches the full 18-step background run, and `POST /tasks/runs/{domain}/{run_id}/continue` returns `409`. Steps must be run individually via `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}`. The fresh-start preview flow (step 1 only) is unaffected by this flag. Set to `true` to restore the old auto-run-everything behavior. |
