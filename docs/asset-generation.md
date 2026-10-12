# Asset Generation — Steps 6 & 7

Step 6 fetches and classifies assets; Step 7 generates the actual files (images, maps, charts) in three parallel sub-steps.

---

## Step 6 — Fetch Assets

`run_fetch_assets()` is implemented inline in `automate.py`. It parses `asset_acquisition.md` and writes a spec file or downloads content for each asset:

| Asset type | Action |
|-----------|--------|
| `ai_video` | Writes `generated.txt` with the Imagen 4 prompt |
| `map` | Writes `map_spec.json` with coordinates and marker data |
| `chart` | Writes `chart_spec.json` with chart type and data |
| `photo` / `video` | Downloads from Pexels API |

All assets are written to `{workspace}/assets/scene_X/asset_Y/`.

---

## Step 7a — Imagen 4 Image Generation

Generates AI images for every `ai_video` asset that has a `generated.txt` prompt file.

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

## Step 7b — Map Generation

Renders geographic maps from `map_spec.json` files written by Step 6.

### Asset manifest format

Step 4/5 prompts must produce map entries in this format:

```json
{
  "type": "map",
  "location": "Berlin, Germany",
  "lat": 52.52,
  "lon": 13.405,
  "zoom": 10,
  "markers": [{"lat": 52.52, "lon": 13.405, "label": "Brandenburg Gate"}],
  "style": "dark"
}
```

### `run_map_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `map_spec.json` files
2. For each file — skip if `map.png` already exists (resumability)
3. Render with Folium → save as HTML → screenshot with headless Playwright → `map.png`

```python
import folium
from playwright.sync_api import sync_playwright

def render_map(spec: dict, output_dir: Path) -> Path:
    m = folium.Map(location=[spec["lat"], spec["lon"]], zoom_start=spec["zoom"])
    for marker in spec.get("markers", []):
        folium.Marker([marker["lat"], marker["lon"]], popup=marker["label"]).add_to(m)
    html_path = output_dir / "map.html"
    m.save(str(html_path))
    png_path = output_dir / "map.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"file://{html_path}")
        page.screenshot(path=str(png_path))
        browser.close()
    return png_path
```

---

## Step 7c — Chart Generation

Renders data charts from `chart_spec.json` files written by Step 6.

### Asset manifest format

```json
{
  "type": "chart",
  "chart_type": "bar",
  "title": "GDP Growth 2015–2024",
  "data": {"labels": ["2015", "2016", "2017"], "values": [2.1, 2.3, 1.8]},
  "style": "cinematic"
}
```

Supported `chart_type` values: `bar`, `line`, `pie`, `area`.

### `run_chart_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `chart_spec.json` files
2. For each file — skip if `chart.png` already exists (resumability)
3. Render with matplotlib on a dark background → `chart.png`

```python
import matplotlib.pyplot as plt

def render_chart(spec: dict, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(16, 9), facecolor="black")
    ax.set_facecolor("black")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    labels = spec["data"]["labels"]
    values = spec["data"]["values"]
    if spec["chart_type"] == "bar":
        ax.bar(labels, values, color="#4A90D9")
    elif spec["chart_type"] == "line":
        ax.plot(labels, values, color="#4A90D9", linewidth=2, marker="o")
    ax.set_title(spec["title"])
    out = output_dir / "chart.png"
    fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="black")
    plt.close()
    return out
```

---

## Step 8 — Animation Prompt Generation

`run_animation_prompt_step()` uses Gemini to write a per-asset cinematic animation description, saved as `animated.txt`. This file feeds directly into Step 9 (RunPod).

### Inputs

- `asset_manifest.md` — parsed for `KEN_BURNS` and `VISUAL_GOAL` per scene/asset block
- `story_script.md` — first ~500 characters used as the narrative vibe (`story_excerpt`)
- `prompts/{domain}/08_animation_prompt.md` — domain-specific template with four placeholders:
  - `{{ken_burns}}` — direction from manifest (e.g. `zoom_in`, `pan_right`)
  - `{{visual_goal}}` — one-sentence visual description from manifest
  - `{{asset_type}}` — derived from filename: `ai_image`, `map`, or `chart`
  - `{{story_excerpt}}` — first 500 chars of the story script for tonal context

### `run_animation_prompt_step(ws)`

1. Parse `asset_manifest.md` → build lookup dict keyed by `(scene_n, asset_n)`
2. Read `story_script.md` → extract first ~500 chars as `story_excerpt`
3. Load `prompts/{domain}/08_animation_prompt.md`
4. Scan `assets/` recursively for `image.png`, `map.png`, `chart.png` (skip `video.mp4`)
5. For each static asset:
   - Skip if sibling `animated.txt` already exists (resumable)
   - Derive scene/asset numbers from folder path (`scene_X/asset_Y`)
   - Look up `KEN_BURNS` + `VISUAL_GOAL` from parsed manifest (defaults: `zoom_in`, empty string)
   - Inject all four variables into the prompt template
   - Call `gemini_generate(prompt)`
   - Write Gemini's one-paragraph response to `scene_X/asset_Y/animated.txt`

### Output example

For a political domain asset with `KEN_BURNS: zoom_out`:

> "Slow pull-back from a close detail of the document revealing the full congressional chamber, camera movement steady and deliberate. The mood is tense and revealing, matching the investigative documentary tone."

---

## Step 8 sidecar — `asset_meta.json`

After writing `animated.txt`, Step 8 also writes a small `asset_meta.json` in the same folder:

```json
{ "ken_burns": "zoom_in", "duration": "10 seconds" }
```

This lets Step 9 access the burn key and duration without re-parsing `asset_manifest.md`.

---

## Step 9 — Video Animation

Each static asset + its Step 8 `animated.txt` prompt is turned into an `animated.mp4` video clip.
It animates the image directly — it does not use ComfyUI.

The per-file animation logic lives in a single shared helper, `_animate_single_asset(txt_file: Path) -> Path`,
used by both the batch step runner and the per-asset endpoint described below. It supports three
backends, selected by config:

1. **Mock** (`MOCK_AI=true`) — writes a placeholder video, no API calls.
2. **OpenRouter** (`USE_OPENROUTER=true`, the default/active path) — calls
   `open_router/video.py`'s `generate_video()`, which submits the image + prompt to OpenRouter's
   async Videos API, polls until completion, and downloads the result.
3. **Self-hosted RunPod pod** (used when `USE_OPENROUTER=false` and `RUNPOD_URL` is set) — talks
   directly to the standalone Wan2.2 I2V server in `server/` (see `docs/runpod-setup.md`) over its
   `/generate`, `/status/{job_id}`, `/download/{job_id}` REST endpoints.

`_animate_single_asset()` raises on failure (no static asset found, missing config, backend error)
rather than swallowing errors — it's the caller's job to decide whether to continue past a failure
or surface it.

### Scope

Only static assets are animated — `video.mp4` files (Pexels stock downloads) are not processed.

### Burn key → motion prefix

The `ken_burns` value from `asset_meta.json` is mapped to a short motion prefix prepended to the
animation prompt:

| `ken_burns` | Motion prefix |
|---|---|
| `zoom_in` | `slow push in,` |
| `zoom_out` | `slow pull back,` |
| `pan_left` | `camera pan left,` |
| `pan_right` | `camera pan right,` |

### Duration

`duration` (e.g. `"10 seconds"`) is parsed to an integer second count and passed to the backend
as the target clip length.

### Batch run — `_run_runpod_animation(step, ws, state)`

This is what runs when step 9 is executed as a whole (e.g. via
`POST /tasks/runs/{domain}/{run_id}/steps/9`, or the full pipeline when
`ENABLE_FULL_PIPELINE=true`):

1. For each `animated.txt` under `{workspace}/assets/`:
   - Skip if sibling `animated.mp4` already exists (resumable)
   - Call `_animate_single_asset(txt_file)`
   - On any exception, log/continue to the next asset (best-effort batch semantics)

The step's completion check uses `"output_marker": "animated.mp4"` in its `STEPS` entry, so
`_output_exists()` correctly reports the step as done once every asset has a video rather than
just checking that the `assets/` directory exists.

### Per-asset animate — `POST /tasks/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/animate`

The frontend no longer exposes a batch "Run"/"Rerun" button for step 9. Instead, each asset gets
its own **Animate** (or **Re-animate**) button, backed by this synchronous endpoint (mirrors the
`regenerate_asset_image` endpoint used for step 7):

1. Resolve `{workspace}/assets/scene_{scene_id}/asset_{asset_id}/`
2. Require an `animated.txt` prompt file to exist (400 if missing)
3. If `animated.mp4` already exists, delete it — re-animation is always unconditional, there's no
   "skip if exists" behavior on this path
4. Call `_animate_single_asset(txt_file)` directly; a raised exception becomes a `422` response
5. Return `{"url": "/tasks/files/{domain}/{run_id}/assets/scene_X/asset_Y/animated.mp4"}`

See `docs/tasks-api.md` for the full request/response/error reference.

### Output

`animated.mp4` in the same folder as the static asset, e.g. `assets/scene_1/asset_1/animated.mp4`.

### Step content — `video_list`

`GET /tasks/runs/{domain}/{run_id}/steps/9/content` returns `{"kind": "video_list", "videos": [...]}`,
built by scanning `{workspace}/assets/` for every `animated.txt` file (i.e. one entry per animatable
asset, not just ones that already have a video). Each entry:

```json
{
  "scene_id": "1",
  "asset_id": "1",
  "label": "scene_1/asset_1",
  "thumbnail_url": "/tasks/files/political/2026-08-20_143022/assets/scene_1/asset_1/image.png",
  "video_url": "/tasks/files/political/2026-08-20_143022/assets/scene_1/asset_1/animated.mp4",
  "status": "done"
}
```

- `thumbnail_url` is the first match of `image.png` > `image.jpg` > `map.png` > `chart.png` found in
  the asset folder, or `null` if none exists.
- `video_url` is set (and `status` is `"done"`) only if `animated.mp4` exists; otherwise `video_url`
  is `null` and `status` is `"pending"`.

The frontend's `VideoSceneViewer.tsx` groups this flat list by `scene_id` → `asset_id` (same
accordion pattern as `ImageSceneViewer.tsx` for step 7) and renders the thumbnail and video
side-by-side per asset, with the per-asset Animate/Re-animate button described above.
