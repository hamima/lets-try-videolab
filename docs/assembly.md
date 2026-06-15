# Assembly — Step 14

Step 14 assembles all produced assets, narration, and music into the final video. Three backends are available, selected via `--assembler`.

---

## Assembler Dispatch

`run_assembler(ws, state)` reads `state["assembler"]` and routes to the correct backend:

```python
def run_assembler(ws: Path, state: dict) -> None:
    assembler = state.get("assembler", "ffmpeg")
    if assembler == "ffmpeg":
        run_script(ws, "assemble.py")
    elif assembler == "replicate":
        from assembler.replicate_assembler import assemble
        assemble(ws, state)
    elif assembler == "runpod":
        from assembler.runpod_assembler import assemble
        assemble(ws, state)
```

Steps 12 and 12b (inventory and timing analysis) always run before Step 14, regardless of assembler:

```python
result = subprocess.run(
    [sys.executable, str(SCRIPTS_DIR / script_name)],
    cwd=str(BASE_DIR),
    env={**os.environ, "WORKSPACE_DIR": str(ws)},
)
```

---

## ffmpeg Assembler (default)

`assemble.py` reads `edl.json` and assembles clips directly:

- Selects and trims asset clips per the EDL
- Applies Ken Burns effect to static images
- Layers narration at full volume + music at 15%
- Exports to `output/final_video.mp4`

---

## Replicate Assembler (`assembler/replicate_assembler.py`)

Managed API — no infrastructure to operate. Pay per prediction.

### EDL-driven mode

For each scene in `edl.json`:
1. Static image (`.png`) → Stable Video Diffusion on Replicate → animated clip matching scene duration
2. Existing video → used as-is
3. All clips → stitched with ffmpeg → narration + music added

```python
import replicate

def image_to_video_clip(image_path: Path, duration: float) -> Path:
    with open(image_path, "rb") as f:
        output = replicate.run(
            "stability-ai/stable-video-diffusion:...",
            input={"input_image": f, "video_length": "25_frames_with_svd_xt"}
        )
    # download output URL → return local clip path
```

**Cost:** ~$0.003–0.005/clip → full 14-scene video ≈ **$0.05–0.07**

### Creative mode

Skips the EDL. For each scene in `scene_plan.md`:
1. Extract scene prompt + reference image (any asset from that scene)
2. Call CogVideoX-5B on Replicate — prompt + reference image as conditioning input
3. Clips → stitched with ffmpeg → narration + music added

```python
def creative_assemble_scene(scene_prompt: str, reference_image: Path) -> Path:
    with open(reference_image, "rb") as f:
        output = replicate.run(
            "zsxkib/cogvideox-5b:...",
            input={
                "prompt": scene_prompt,
                "image": f,
                "num_frames": 49,
                "fps": 8,
            }
        )
```

**Cost:** ~$0.05/clip → full 14-scene video ≈ **$0.70**

---

## RunPod Assembler (`assembler/runpod_assembler.py`)

Self-hosted models on a rented GPU pod. Same two modes, but HTTP requests go to the pod's local endpoint instead of Replicate's API.

### Pod lifecycle

```python
import runpod

def start_pod() -> tuple[str, str]:
    pod = runpod.create_pod(
        name="vidlife-assembler",
        image_name="runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04",
        gpu_type_id="NVIDIA A100 80GB PCIe",
    )
    endpoint = wait_for_pod_ready(pod["id"])
    return pod["id"], endpoint

def terminate_pod(pod_id: str) -> None:
    runpod.terminate_pod(pod_id)
```

Pod starts at the beginning of Step 14 and is terminated immediately after `final_video.mp4` is written.

### EDL-driven mode

Same logic as Replicate EDL mode — self-hosted SVD endpoint on the pod.

**Cost:** ~$0.74/hr on A100 → 14-scene EDL run ≈ 15 min → **~$0.19/video**

### Creative mode

Self-hosts Wan2.1-14B — highest quality open source video model as of mid-2025.

**Cost:** ~45 min on A100 → **~$0.56/video**

---

## Comparison

| Metric | ffmpeg | Replicate / EDL | Replicate / creative | RunPod / EDL | RunPod / creative |
|--------|--------|-----------------|----------------------|--------------|-------------------|
| Cost/video | ~$0 | ~$0.06 | ~$0.70 | ~$0.19 | ~$0.56 |
| Time/video | ~30s | ~8 min | ~25 min | ~15 min | ~45 min |
| Ops overhead | None | None | None | Pod mgmt | Pod mgmt |
| Uses EDL | Yes | Yes | No | Yes | No |
| Output quality | Deterministic | Animated stills | AI-generated | Animated stills | Highest quality |

> Fill in actual measured values during benchmarking. See `replicate-runpod-plan.md` for the full evaluation plan.
