# Separate AI and Server Code into Distinct Packages

Create two new top-level packages at the project root, leaving the original `server/` folder untouched:

- **`ai/`** — everything ML/inference: pipeline loading, model configuration, inference execution, and frame calculation. Receives all config values as parameters (no direct config file access). Has its own `requirements.txt` for ML dependencies.
- **`backend/`** — new API/server code: FastAPI app, endpoints, job state, idle watchdog, config loading. Imports from `ai/` and passes config values in. Has its own `requirements.txt` for API dependencies and its own `setup.sh`.

The original `server/` folder is **not modified** — it remains as-is for reference.

Key decisions made:
- `ai/wan_i2v.py` exposes pure functions (`load_pipeline`, `run_inference`) that return results rather than mutating job state — keeping AI code decoupled from server concerns.
- `JobState` and job tracking live in `backend/server.py`.
- `server_config.json` and config loading live in `backend/`.
- Single flat `ai/` module (no sub-packages) since there is only one model.
- Entry point is `backend/server.py`.

---

## Create the `ai/` package

Create the new `ai/` directory at the project root with `__init__.py` and `wan_i2v.py`.

### Add `ai/__init__.py`

Empty init file to make `ai` a Python package.

### Extract AI logic into `ai/wan_i2v.py`

Move the following from `server/server.py` into `ai/wan_i2v.py`:

- Imports: `torch`, `diffusers` (`AutoencoderKLWan`, `WanImageToVideoPipeline`, `export_to_video`), `PIL`, `gc`, `io`, `threading`
- `_clear_gpu()` — GPU memory cleanup helper
- `_configure_memory(pipe, memory_mode)` — accepts `memory_mode` as a parameter instead of reading from `cfg`
- `_load_pipeline(model_id, memory_mode)` — accepts `model_id` and `memory_mode` as parameters; manages the global `_pipe` and `_pipe_lock` internally
- `_nearest_valid_frames(duration_seconds, fps)` — accepts `fps` as a parameter
- `run_inference(job_id, prompt, image_bytes, num_frames, width, height, seed, negative_prompt, output_dir, num_inference_steps, guidance_scale, guidance_scale_2, model_id, memory_mode, fps)` — renamed from `_run_inference`; instead of mutating `_jobs[job_id]`, returns `output_path: Path` on success or raises `Exception` on failure; all config values received as parameters

All module-level globals inside `ai/wan_i2v.py` (`_pipe`, `_pipe_lock`) are internal implementation details and not exported.

### Add `ai/requirements.txt`

ML/GPU dependencies split out from the current `server/requirements.txt`:

```
--extra-index-url https://download.pytorch.org/whl/cu121
torch==2.5.1
torchvision==0.20.1
diffusers>=0.35.0
transformers>=4.49.0
accelerate>=1.1.0
safetensors>=0.4.5
huggingface-hub[hf-xet]>=0.27.0
sentencepiece>=0.2.0
imageio>=2.34.0
imageio-ffmpeg>=0.5.1
Pillow>=10.0.0
ftfy>=6.2.0
tiktoken>=0.7.0
protobuf>=5.28.0
```

---

## Create `backend/` package

Create the new `backend/` directory at the project root. Copy `server/server.py`, `server/server_config.json`, and `server/setup.sh` as the starting point, then modify them.

### Add `backend/server.py`

Based on `server/server.py` but with all AI logic removed and replaced with imports from `ai/`:

- Remove: all `torch`, `diffusers`, `PIL` imports; `_clear_gpu`, `_configure_memory`, `_load_pipeline`, `_nearest_valid_frames`, `_run_inference`; the `_pipe` and `_pipe_lock` globals
- Add at the top:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.wan_i2v import run_inference, nearest_valid_frames
```

- Replace the `_run_inference` thread target with a local wrapper that:
  1. Sets `_jobs[job_id].status = "processing"`
  2. Calls `run_inference(...)` passing all config values from `cfg`
  3. On success: sets `job.status = "done"`, `job.video_path = returned_path`, calls `_touch_activity()`
  4. On exception: sets `job.status = "failed"`, `job.error = str(exc)`

Config values passed into `run_inference`:
- `output_dir=OUTPUT_DIR`
- `num_inference_steps=cfg["num_inference_steps"]`
- `guidance_scale=cfg["guidance_scale"]`
- `guidance_scale_2=cfg["guidance_scale_2"]`
- `model_id=cfg["i2v_model_id"]`
- `memory_mode=cfg["memory_mode"]`
- `fps=cfg["fps"]`

### Add `backend/server_config.json`

Copy from `server/server_config.json` unchanged.

### Add `backend/requirements.txt`

API-only dependencies:

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.12
```

### Add `backend/setup.sh`

Based on `server/setup.sh` but with the pip install block replaced by two sequential installs:

```bash
echo "=== Step 4a: Install AI/inference dependencies ==="
python -m pip install --no-cache-dir -r "$SCRIPT_DIR/../ai/requirements.txt"

echo "=== Step 4b: Install backend/API dependencies ==="
python -m pip install --no-cache-dir -r "$SCRIPT_DIR/requirements.txt"
```

The existing combined torch+fastapi install block is removed since dependencies are now split across both requirements files. All other setup logic (storage mount check, GPU check, venv creation, model download, config patching, server start) is preserved verbatim, with paths updated from `$SCRIPT_DIR/server.py` to `$SCRIPT_DIR/server.py` (no change needed — entry point filename is the same).

#### Acceptance criteria
- Running `bash backend/setup.sh` installs all dependencies from both `ai/requirements.txt` and `backend/requirements.txt`
- Running `bash backend/setup.sh --start-only` works as before
- The server starts and the `/generate` endpoint works end-to-end
- `server/` is completely untouched
