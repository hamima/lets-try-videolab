# Replicate & RunPod Evaluation — Open Source Model Integration

## Overview

Evaluate Replicate and RunPod as platforms for open source models to handle two new capabilities in the VidLife pipeline:

1. **New asset types** — AI-generated maps and charts (extending Step 6)
2. **Final video composition** — replace/augment the current `assemble.py` (Step 14) with model-driven assembly

The evaluation compares both platforms on cost, capability, and integration complexity, and tests two composition modes: **EDL-driven** (deterministic, Gemini's `edl.json` drives timing) and **creative** (model makes composition decisions). Both modes are added to `automate.py` via an `--assembler` flag (`ffmpeg` | `replicate` | `runpod`).

**Key architectural insight:** Generative models (video diffusion) excel at creating content from scratch. They do NOT natively "assemble existing asset files" the way ffmpeg does. The plan accounts for this — AI composition means AI-generated transitions, style layers, and creative bridging between assets, with the actual cut timing still anchored to narration timing and the EDL.

**Output:** Research first (feasibility + cost matrix), then implementation.

---

## Research: Model Landscape Survey

Understand what open source models are available, what they actually do, and how they compare before writing any code.

### Survey video generation/composition models

| Model | Available on | Approach | Strengths | Weaknesses |
|-------|-------------|----------|-----------|------------|
| **CogVideoX-5B** | Replicate, RunPod | Text + image → video | High quality, good motion coherence | Generates from scratch, slow (~90s/5s clip) |
| **Wan2.1-T2V-14B** | Replicate, RunPod | Text → video | Strong motion, 720p, best open source quality | Cannot directly use existing asset files |
| **LTX-Video** | Replicate, RunPod | Text + image → video | Very fast (~2s/5s clip on H100) | Lower quality, short clips |
| **Mochi 1** | Replicate | Text → video | Smooth, high-fidelity motion | Slow, large (10B params) |
| **Stable Video Diffusion (SVD)** | Replicate, RunPod | Image → 4s video | Good for still-to-motion transitions | Max 4s, no audio, image input only |
| **AnimateDiff** | RunPod | Image sequence → video | Controllable animation from images | Needs ComfyUI orchestration |
| **ComfyUI** | RunPod (self-hosted) | Orchestration layer | Chains any model, can ingest existing files | Complex setup, no managed API |

**Key finding to validate:** For assembling *existing* asset files (images, clips), diffusion models don't natively accept a file list and compose them. The real use case is: use the asset as a conditioning input (img2img, image-to-video) to generate a stylistically consistent clip, then stitch with ffmpeg. The EDL still controls timing.

### Survey map generation options

Dedicated AI map generation models do not exist on Replicate as of mid-2025. Options:

| Approach | Tool | Accuracy | AI involvement |
|----------|------|----------|---------------|
| **Programmatic** | Folium, Plotly geo, Mapbox Static API | Geographically accurate | None — pure code |
| **AI-stylized** | FLUX.1-dev (Replicate) — img2img from a base map | Artistic, not accurate | Style transfer only |
| **Prompt-generated** | FLUX.1 / SDXL — text prompt describing a map | Creative, not accurate | Full generation |

**Recommended path:** Generate base map programmatically (Folium/Plotly from coordinates extracted by Gemini from the scene plan), then optionally pass through FLUX.1 img2img for visual style. The Gemini step already produces scene context — extract location data from it.

### Survey chart generation options

Same pattern as maps:

| Approach | Tool | Data accuracy | AI involvement |
|----------|------|--------------|---------------|
| **Programmatic** | matplotlib, plotly, seaborn | Exact | None |
| **AI-stylized** | FLUX.1 img2img from matplotlib output | Exact data, styled | Style transfer |
| **Prompt-generated** | FLUX.1 / SDXL | No data accuracy | Full generation |

**Recommended path:** matplotlib/plotly for data accuracy (Gemini extracts data from scene context), optional AI style pass.

### Cost comparison matrix

Build a per-run cost estimate for a typical video (~14 scenes, ~3.5 min).

| Operation | Replicate | RunPod (A100, $0.74/hr) |
|-----------|-----------|------------------------|
| Image → 5s video clip (SVD) | ~$0.003/clip | ~$0.002/clip |
| Text → 5s video (CogVideoX) | ~$0.05/clip | ~$0.03/clip |
| Text → 5s video (LTX-Video) | ~$0.004/clip | ~$0.002/clip |
| FLUX.1 img2img (map/chart style) | ~$0.003/image | ~$0.001/image |
| 14 scenes full run (CogVideoX) | ~$0.70 | ~$0.42 |
| 14 scenes full run (LTX-Video) | ~$0.056 | ~$0.028 |

**Replicate pros:** Zero ops, instant API, pay-per-prediction, no pod management.
**RunPod pros:** 40–60% cheaper at volume, run any model not on Replicate, full control.
**RunPod cons:** Pod spin-up time (~2–5 min), need to manage your own API server.

### Deliverable

A `research/model-evaluation.md` document with:
- Confirmed model list per platform with actual API endpoints
- Actual cost measurements from test runs (not estimates)
- Capability verdict: which model best handles image-to-video conditioning for asset composition
- Recommendation on which platform to implement first

---

## Implement new asset types: Maps and Charts (Step 6 extension)

Extend `run_fetch_assets()` in `automate.py` to handle two new asset types: `map` and `chart`. These are generated programmatically (from data Gemini extracts) and optionally stylized via FLUX.1 on Replicate.

### Extend asset manifest and acquisition prompts

Update `prompts/{domain}/04_asset_planning.md` and `05_asset_acquisition.md` to recognize and plan for `map` and `chart` asset types.

Asset manifest entry format for maps:
```json
{
  "type": "map",
  "location": "Berlin, Germany",
  "zoom": 10,
  "markers": [{"lat": 52.52, "lon": 13.405, "label": "Brandenburg Gate"}],
  "style": "dark"
}
```

Asset manifest entry format for charts:
```json
{
  "type": "chart",
  "chart_type": "bar",
  "title": "GDP Growth 2015–2024",
  "data": {"labels": ["2015","2016",...], "values": [2.1, 2.3, ...]},
  "style": "cinematic"
}
```

### Implement `generate_map_asset(spec, output_dir)`

1. Parse `map_spec.json` written by Step 6
2. Use Folium to render an HTML map → convert to PNG via headless Chrome (`playwright` or `selenium`)
3. If `style` is set and Replicate key is available, pass through FLUX.1 img2img for cinematic styling
4. Save as `map.png` in the asset directory

```python
import folium
from playwright.sync_api import sync_playwright

def generate_map_asset(spec: dict, output_dir: Path) -> Path:
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

### Implement `generate_chart_asset(spec, output_dir)`

1. Parse chart spec from asset manifest
2. Render with matplotlib (bar, line, pie, area) → save as PNG
3. Optionally animate: render one frame per data point → ffmpeg → chart_build.mp4
4. If `style` is set, pass PNG through FLUX.1 img2img

```python
import matplotlib.pyplot as plt
import matplotlib.animation as animation

def generate_chart_asset(spec: dict, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(16, 9), facecolor='black')
    ax.set_facecolor('black')
    # ... render based on spec["chart_type"]
    out = output_dir / "chart.png"
    fig.savefig(out, dpi=120, bbox_inches='tight')
    plt.close()
    return out
```

---

## Implement `--assembler` flag and Replicate assembler

Add `--assembler replicate|runpod|ffmpeg` to `automate.py`. The existing Step 14 (`assemble.py`) becomes the `ffmpeg` mode. New modes call cloud GPU APIs.

### Add CLI flag

```python
parser.add_argument("--assembler", choices=["ffmpeg", "replicate", "runpod"],
                    default="ffmpeg", help="Assembly backend for Step 14")
```

Pass `assembler` into the step 14 runner. If `ffmpeg`, call existing `assemble.py`. Otherwise, call the new assembler module.

### Implement Replicate assembler (`assembler/replicate_assembler.py`)

Two modes, both produce `final_video.mp4`.

#### EDL-driven mode

The EDL from `edl.json` controls which asset plays when and for how long. For each EDL entry:
1. If asset is a static image → call SVD (Stable Video Diffusion) on Replicate to convert to a short animated clip matching the narration duration for that scene
2. If asset is already a video → use as-is (or optionally run through LTX-Video for style consistency)
3. Collect all clips → stitch with ffmpeg → add narration + music

```python
import replicate

def image_to_video_clip(image_path: Path, duration: float) -> Path:
    with open(image_path, "rb") as f:
        output = replicate.run(
            "stability-ai/stable-video-diffusion:...",
            input={"input_image": f, "video_length": "25_frames_with_svd_xt"}
        )
    # download output URL → local clip
    ...
```

#### Creative mode

Pass assets + narration transcript + scene plan to a capable model (CogVideoX or Wan2.1). The model generates each scene clip from a text prompt derived from the scene plan, using the prepared asset image as a style/composition reference (img2img). Gemini's EDL is not used — the model decides framing and motion.

```python
def creative_assemble_scene(scene_prompt: str, reference_image: Path) -> Path:
    with open(reference_image, "rb") as f:
        output = replicate.run(
            "zsxkib/cogvideox-5b:...",
            input={
                "prompt": scene_prompt,
                "image": f,          # reference/conditioning
                "num_frames": 49,
                "fps": 8,
            }
        )
    ...
```

### Implement RunPod assembler (`assembler/runpod_assembler.py`)

Same two modes, but calls a self-hosted ComfyUI or model server on a RunPod pod.

#### Pod management

```python
import runpod

def start_pod(model: str = "wan2.1") -> str:
    pod = runpod.create_pod(
        name="vidlife-assembler",
        image_name="runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
        gpu_type_id="NVIDIA A100 80GB PCIe",
        ...
    )
    return pod["id"]

def wait_for_pod_ready(pod_id: str) -> str:
    # poll until status == RUNNING, return endpoint URL
    ...
```

#### EDL-driven mode (RunPod)

Same logic as Replicate EDL mode, but HTTP requests go to the self-hosted model endpoint instead of Replicate's API. Pod is started at the beginning of assembly and terminated when done.

#### Creative mode (RunPod)

Self-host Wan2.1-14B (highest quality open source video model as of mid-2025) for scene generation. At ~$0.74/hr on A100, a full 14-scene video at ~3 min/scene generates in under 1 hr → ~$0.74/video vs Replicate's ~$0.70 at similar quality. RunPod wins at volume.

---

## Benchmark and comparison report

After both assemblers are implemented and tested on at least 2 full pipeline runs each:

### Metrics to capture per run

- Total wall-clock time (Step 14 only)
- Cost (API charges logged per request)
- Output video quality (subjective 1–5 rating + SSIM vs ffmpeg baseline)
- EDL mode vs creative mode quality comparison
- Failure rate (API timeouts, model errors)

### Comparison matrix format

| Metric | ffmpeg (baseline) | Replicate/SVD (EDL) | Replicate/CogVideoX (creative) | RunPod/Wan2.1 (EDL) | RunPod/Wan2.1 (creative) |
|--------|------------------|---------------------|-------------------------------|---------------------|--------------------------|
| Cost/video | ~$0 | ~$0.05 | ~$0.70 | ~$0.01 + pod | ~$0.74 + pod |
| Time/video | ~30s | ~8 min | ~25 min | ~15 min | ~45 min |
| Quality (1–5) | TBD | TBD | TBD | TBD | TBD |
| Ops complexity | None | None | None | Pod mgmt | Pod mgmt |

### Deliverable

`research/benchmark-results.md` — fill in actual numbers, add video samples, write recommendation for which backend to use as default going forward.
