# Asset Generation — Steps 6 & 7

Step 6 fetches and classifies assets; Step 7 generates the actual image files in parallel sub-steps.

---

## Step 6 — Fetch Assets

`_run_fetch_assets()` parses `asset_acquisition.md` and writes a spec/prompt file for each asset:

| Asset type | Action |
|-----------|--------|
| `ai_video` / `ai_image` | Writes `generated.txt` with the AI image prompt (both types start as an Imagen-generated still; the difference is in how they're later animated at Step 9) |

All assets are written to `{workspace}/assets/scene_X/asset_Y/`.

### Sidecar — `asset_meta.json`

For **every** asset (not just `ai_video`), Step 6 also writes `asset_meta.json` in the same folder:

```json
{
  "asset_type": "ai_image",
  "ken_burns": "zoom_in",
  "intensity": 0.2,
  "duration": "16 seconds"
}
```

- `asset_type` — one of `ai_video`, `ai_image`, carried over from `asset_acquisition.md`'s `TYPE:` field.
- `ken_burns` — direction, parsed from the manifest's `KEN_BURNS:` field (defaults to `zoom_in` if missing/invalid); **`null` for `ai_video`** assets, since those are animated by an AI model instead.
- `intensity` — `0.1`–`0.3`, parsed from `INTENSITY:` (defaults to `0.2` if missing/out of range); **`null` for `ai_video`** assets.
- `duration` — the per-asset duration string (e.g. `"16 seconds"`), carried over unchanged from the manifest.

This sidecar is the single source of truth Step 8 and Step 9 use to decide how each asset is animated, without re-parsing `asset_manifest.md`/`asset_acquisition.md`.

---

## Step 7 — Imagen 4 Image Generation

Generates AI images for every `ai_video`/`ai_image` asset that has a `generated.txt` prompt file.

### `run_imagen_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `generated.txt` files
2. For each file — skip if `image.png` already exists (resumability)
3. Call Imagen 4:

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)
response = client.models.generate_images(
    model=IMAGEN_MODEL,   # "imagen-4.0-generate-001"
    prompt=image_prompt,
    config=types.GenerateImagesConfig(number_of_images=1),
)
```

4. Save as `image.png` in the same directory as `generated.txt`
5. Log: `scene_X/asset_Y → image.png`

---

## Step 8 — Animation Prompt Generation (`ai_video` only)

`_run_animation_prompt_step()` uses Gemini to write a per-asset cinematic motion prompt, saved as
`animated.txt`, for **`ai_video` assets only**. `ai_image` assets skip step 8 entirely — their
motion is already fully determined by the `ken_burns`/`intensity` fields written into
`asset_meta.json` at Step 6, so there's nothing for Gemini to generate.

### Inputs

- `asset_manifest.md` — parsed (via `_parse_asset_manifest()`) for `VISUAL_GOAL` and `DURATION` per
  scene/asset block
- `generated.txt` — the exact Imagen prompt used to generate the asset's `image.png` at Step 7;
  this is the ground-truth description of what's actually in the frame
- `story_script.md` — first ~500 characters used as the narrative vibe (`story_excerpt`)
- `prompts/{domain}/08_animation_prompt.md` — domain-specific template with five placeholders:
  - `{{image_prompt}}` — the asset's `generated.txt` contents; the model must only describe motion
    applied to this exact image, not invent new scene content
  - `{{visual_goal}}` — one-sentence visual description from the manifest (tone/context only)
  - `{{asset_type}}` — always `"ai_video"` at this step
  - `{{duration}}` — the asset's duration string, read from `asset_meta.json`
  - `{{story_excerpt}}` — first 500 chars of the story script for tonal context

### `_run_animation_prompt_step(ws)`

1. Parse `asset_manifest.md` → build a `visual_goal`/`duration` lookup dict keyed by `(scene_n, asset_n)`
2. Read `story_script.md` → extract first ~500 chars as `story_excerpt`
3. Load `prompts/{domain}/08_animation_prompt.md`
4. Scan `assets/` recursively for every `asset_meta.json` — **skip any whose `asset_type` is not
   `"ai_video"`**
5. For each `ai_video` asset:
   - Skip if sibling `animated.txt` already exists (resumable)
   - Skip if a sibling `animation_blocked.txt` exists (previous Gemini call failed)
   - Derive scene/asset numbers from the folder path (`scene_X/asset_Y`)
   - Read the asset's `generated.txt` (image prompt) — if missing, write to
     `animation_blocked.txt` and skip (an `ai_video` asset's motion can't be grounded without
     knowing what's actually in the image)
   - Look up `visual_goal` from the parsed manifest; read `duration` from `asset_meta.json`
   - Inject all five variables into the prompt template and call `_gemini_generate(prompt)`
   - On exception, write the error to `animation_blocked.txt` and continue to the next asset
   - Otherwise write Gemini's one-paragraph response to `scene_X/asset_Y/animated.txt`

This step produces an **image-to-video** motion prompt, not a text-to-video scene description —
the video model (Wan2.1 via RunPod/OpenRouter) takes the static `image.png` as its starting frame,
so `animated.txt` must only describe camera motion and small in-frame changes applied to the
subject already present in `generated.txt`. There is no Ken-Burns translation table or `ANIMATE`
flag involved here — the asset-type gate (`asset_type == "ai_video"`) is the only filter.

### Output example

> "Over 10 seconds, the camera pushes forward between towering rows of humming server racks, their status lights pulsing in the dark. The mood is cold, vast, and faintly ominous — a machine civilization at scale."

---

## Step 9 — Video Animation

Every asset (not just `ai_video`) gets an `animated.mp4` at Step 9. The per-asset logic lives in a
single shared helper, `_animate_single_asset(asset_dir: Path) -> Path`, used by both the batch step
runner and the per-asset endpoint described below. It branches on `asset_meta.json`'s `asset_type`:

- **`ai_video`** — resolves `animated.txt` (from Step 8) + the static base image, then calls an AI
  video backend:
  1. **Mock** (`MOCK_AI=true`) — writes a placeholder video, no API calls.
  2. **OpenRouter** (`USE_OPENROUTER=true`, the default/active path) — calls
     `open_router/video.py`'s `generate_video()`, which submits the image + prompt to OpenRouter's
     async Videos API, polls until completion, and downloads the result.
  3. **Self-hosted RunPod pod** (used when `USE_OPENROUTER=false` and `RUNPOD_URL` is set) — talks
     directly to the standalone Wan2.2 I2V server in `server/` (see `docs/runpod-setup.md`) over its
     `/generate`, `/status/{job_id}`, `/download/{job_id}` REST endpoints.
- **`ai_image`** — renders a Ken-Burns zoom/pan clip directly in Python via `backend/ken_burns.py`'s
  `render_ken_burns()`, using the static base image plus `asset_meta.json`'s `ken_burns` direction,
  `intensity`, and `duration`. No LLM or external API call is involved — this path is pure MoviePy.

`_animate_single_asset()` raises on failure (no static asset found, missing config, backend error)
rather than swallowing errors — it's the caller's job to decide whether to continue past a failure
or surface it.

### `backend/ken_burns.py` — `render_ken_burns()`

```python
def render_ken_burns(
    image_path: Path, out_path: Path, direction: str, intensity: float,
    duration_seconds: float, width: int = 1920, height: int = 1080,
) -> Path:
    ...
```

- `direction` — one of `zoom_in`, `zoom_out`, `pan_left`, `pan_right`
- `intensity` — `0.1`–`0.3`, how strong the zoom/pan motion is
- Resizes/crops the source image onto an oversized canvas (`width`/`height` scaled up by
  `1 + intensity`), then crops a fixed-size window out of that canvas per frame — shrinking/growing
  the window for zoom, or sliding it for pan. This keeps every output frame exactly `width`×`height`,
  which MoviePy/ffmpeg require for `write_videofile()`; animating `.resized()`/`.with_position()`
  directly on a clip does not reliably produce a constant frame size.
- Covered by a smoke test (`backend/tests/test_ken_burns.py`) parametrized over all four directions,
  plus a standalone visual preview script (`backend/tests/preview_ken_burns.py`) for manually
  inspecting motion and duration.

### Scope

Every asset gets exactly one `animated.mp4`, via whichever of the two paths above matches its
`asset_type`. The video/image split slider (`video_split_percent`, see `docs/llm-steps.md`)
controls what fraction of total narration time is assigned to `ai_video` at Step 4 — that's the
only thing that determines which assets take the AI-animation path vs. the Ken-Burns path.

### Duration

`duration` (e.g. `"10 seconds"`) is parsed to an integer second count via `_duration_to_seconds()`
and passed to whichever backend is used as the target clip length.

### Batch run — `_run_video_animation(step, ws, state)`

This is what runs when step 9 is executed as a whole (e.g. via
`POST /tasks/runs/{domain}/{run_id}/steps/9`, or the full pipeline when
`ENABLE_FULL_PIPELINE=true`):

1. For each `asset_meta.json` under `{workspace}/assets/`:
   - Skip if sibling `animated.mp4` already exists (resumable)
   - Call `_animate_single_asset(asset_dir)`
   - On any exception, log/continue to the next asset (best-effort batch semantics)

The step's completion check uses `"output_marker": "animated.mp4"` in its `STEPS` entry, so
`_output_exists()` correctly reports the step as done once every asset has a video rather than
just checking that the `assets/` directory exists.

### Per-asset animate — `POST /tasks/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/animate`

In addition to the batch Run/Rerun button on the step itself (same as every other step), every asset
gets its own **Animate** (or **Re-animate**) button, backed by this synchronous endpoint (mirrors the
`regenerate_asset_image` endpoint used for step 7). This works for both asset types — `ai_video`
re-runs the AI video model, `ai_image` re-renders the Ken-Burns clip:

1. Resolve `{workspace}/assets/scene_{scene_id}/asset_{asset_id}/`
2. Read `asset_meta.json`. For `ai_video` assets, require an `animated.txt` prompt file to exist
   (400 if missing); for `ai_image`, the static `image.png` file is the only requirement.
3. If `animated.mp4` already exists, delete it — re-animation is always unconditional, there's no
   "skip if exists" behavior on this path
4. Call `_animate_single_asset(asset_dir)` directly; a raised exception becomes a `422` response
5. Return `{"url": "/tasks/files/{domain}/{run_id}/assets/scene_X/asset_Y/animated.mp4"}`

See `docs/tasks-api.md` for the full request/response/error reference.

### Output

`animated.mp4` in the same folder as the static asset, e.g. `assets/scene_1/asset_1/animated.mp4`.

### Step content — `video_list`

`GET /tasks/runs/{domain}/{run_id}/steps/9/content` returns `{"kind": "video_list", "videos": [...]}`,
built by scanning `{workspace}/assets/` for every `asset_meta.json` file (i.e. one entry per asset,
Ken-Burns or `ai_video` alike). Each entry:

```json
{
  "scene_id": "1",
  "asset_id": "1",
  "label": "scene_1/asset_1",
  "thumbnail_url": "/tasks/files/political/2026-08-20_143022/assets/scene_1/asset_1/image.png",
  "prompt": "",
  "video_url": "/tasks/files/political/2026-08-20_143022/assets/scene_1/asset_1/animated.mp4",
  "status": "done",
  "asset_type": "ai_image"
}
```

- `thumbnail_url` is `image.png` if present in the asset folder, or `null` if none exists.
- `video_url` is set (and `status` is `"done"`) only if `animated.mp4` exists; otherwise `video_url`
  is `null` and `status` is `"pending"`.
- `prompt` is the content of `animated.txt` if present (only for `ai_video` assets), else an empty string.
- `asset_type`, `ken_burns`, `intensity`, and `duration` are read straight from `asset_meta.json`.

The frontend's `VideoSceneViewer.tsx` groups this flat list by `scene_id` → `asset_id` (same
accordion pattern as `ImageSceneViewer.tsx` for step 7) and renders the thumbnail and video
side-by-side per asset. `AssetVideoCard` always shows the Animate/Re-animate button; for every
`ai_image` asset it additionally renders a `Ken Burns: Zoom In`-style badge (direction, intensity,
duration) next to the button, since those assets' motion is driven entirely by `asset_meta.json`
rather than a per-asset prompt.
