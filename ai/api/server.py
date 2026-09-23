#!/usr/bin/env python3
"""
FastAPI server — Wan 2.2 I2V direct inference.

Endpoints:
  POST /generate
      prompt=<text>
      image=<file>

  GET /status/{job_id}
  GET /download/{job_id}
  GET /config

Example:
    curl -X POST http://localhost:8080/generate \
      -F "prompt=The camera slowly pushes forward while the subject smiles" \
      -F "image=@input.png"

Auto-shutdown:
  The server shuts down after idle_timeout_minutes of inactivity.
  Set idle_timeout_minutes=0 to disable.
"""

import json
import os
import signal
import sys
import threading
import time
import uuid

from pathlib import Path
from typing import Dict, Optional

import uvicorn

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse

# Project root is three levels up: ai/api/server.py → ai/api → ai → project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ai.models.wan_i2v import nearest_valid_frames, run_inference


# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

_CONFIG_DEFAULTS: dict = {

    # ---------------------------------------------------------
    # Model
    # ---------------------------------------------------------

    "i2v_model_id": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",

    # ---------------------------------------------------------
    # Server
    # ---------------------------------------------------------

    "host": "0.0.0.0",
    "port": 8080,

    "idle_timeout_minutes": 30,

    "output_dir": "/tmp/wan22_outputs",

    # ---------------------------------------------------------
    # Video defaults
    # ---------------------------------------------------------

    "width": 1280,
    "height": 720,

    # Wan frame counts should normally follow 4n+1.
    # 81 frames @ 16 fps = ~5 seconds.
    "num_frames": 81,

    "fps": 16,

    # ---------------------------------------------------------
    # Diffusion
    # ---------------------------------------------------------

    "num_inference_steps": 40,

    # Wan 2.2 uses high-noise and low-noise transformers.
    "guidance_scale": 4.0,
    "guidance_scale_2": 3.0,

    # ---------------------------------------------------------
    # Memory
    # ---------------------------------------------------------

    # Options:
    #   "cuda"        → pipe.to("cuda")
    #   "cpu_offload" → model CPU offloading
    #
    # cpu_offload uses less VRAM but is slower.
    "memory_mode": "cuda",

    # ---------------------------------------------------------
    # Prompt defaults
    # ---------------------------------------------------------

    "negative_prompt": (
        "overexposed, static, blurry, low quality, worst quality, "
        "jpeg artifacts, text, subtitles, watermark, deformed, "
        "disfigured, malformed limbs, poorly drawn hands, "
        "poorly drawn face, frozen image"
    ),
}


_CONFIG_PATH = Path(
    os.environ.get(
        "SERVER_CONFIG",
        Path(__file__).parent / "server_config.json",
    )
)


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        stored = json.loads(_CONFIG_PATH.read_text())
        return {**_CONFIG_DEFAULTS, **stored}

    _CONFIG_PATH.write_text(json.dumps(_CONFIG_DEFAULTS, indent=2))
    print(f"[config] Created default config at {_CONFIG_PATH}")
    return dict(_CONFIG_DEFAULTS)


cfg = _load_config()

if os.environ.get("WAN_I2V_MODEL_ID"):
    cfg["i2v_model_id"] = os.environ["WAN_I2V_MODEL_ID"]

print("[config]", json.dumps(cfg, indent=2))


# ─────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(cfg["output_dir"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────

class JobState:

    def __init__(self) -> None:
        self.status: str = "pending"
        # pending | processing | done | failed

        self.video_path: Optional[Path] = None

        self.error: Optional[str] = None

        self.created_at = time.time()


_jobs: Dict[str, JobState] = {}

_jobs_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────
# Activity / shutdown
# ─────────────────────────────────────────────────────────────

_last_activity: float = time.monotonic()

_activity_lock = threading.Lock()


def _touch_activity() -> None:
    global _last_activity

    with _activity_lock:
        _last_activity = time.monotonic()


def _has_active_jobs() -> bool:
    with _jobs_lock:
        return any(
            j.status in ("pending", "processing")
            for j in _jobs.values()
        )


def _idle_watchdog() -> None:
    timeout = cfg["idle_timeout_minutes"]

    if timeout <= 0:
        return

    timeout_secs = timeout * 60

    print(
        f"[watchdog] Auto-shutdown after "
        f"{timeout} min inactivity"
    )

    while True:
        time.sleep(60)

        with _activity_lock:
            idle_secs = time.monotonic() - _last_activity

        if idle_secs >= timeout_secs and not _has_active_jobs():
            print(
                f"[watchdog] Idle for "
                f"{idle_secs / 60:.1f} min "
                "— shutting down"
            )
            os.kill(os.getpid(), signal.SIGTERM)
            return


# ─────────────────────────────────────────────────────────────
# Inference thread wrapper
# ─────────────────────────────────────────────────────────────

def _run_job(
    job_id: str,
    prompt: str,
    image_bytes: bytes,
    num_frames: int,
    width: int,
    height: int,
    seed: Optional[int],
    negative_prompt: str,
) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "processing"

    try:
        out_path = run_inference(
            job_id=job_id,
            prompt=prompt,
            image_bytes=image_bytes,
            num_frames=num_frames,
            width=width,
            height=height,
            seed=seed,
            negative_prompt=negative_prompt,
            output_dir=OUTPUT_DIR,
            num_inference_steps=cfg["num_inference_steps"],
            guidance_scale=cfg["guidance_scale"],
            guidance_scale_2=cfg["guidance_scale_2"],
            model_id=cfg["i2v_model_id"],
            memory_mode=cfg["memory_mode"],
            fps=cfg["fps"],
        )

        with _jobs_lock:
            job = _jobs[job_id]
            job.status = "done"
            job.video_path = out_path

        _touch_activity()

    except Exception as exc:
        with _jobs_lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.error = str(exc)

        print(f"[job {job_id}] FAILED: {exc}")


# ─────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────

app = FastAPI(title="Wan 2.2 I2V Server")


@app.middleware("http")
async def _track_activity(request: Request, call_next):
    _touch_activity()
    return await call_next(request)


@app.on_event("startup")
def _start_watchdog():
    thread = threading.Thread(target=_idle_watchdog, daemon=True)
    thread.start()


# ─────────────────────────────────────────────────────────────
# Config endpoint
# ─────────────────────────────────────────────────────────────

@app.get("/config")
def get_config():
    with _activity_lock:
        idle_secs = time.monotonic() - _last_activity

    return {
        **cfg,
        "config_path": str(_CONFIG_PATH),
        "idle_seconds": round(idle_secs),
        "auto_shutdown": cfg["idle_timeout_minutes"] > 0,
    }


# ─────────────────────────────────────────────────────────────
# Generate
# ─────────────────────────────────────────────────────────────

@app.post("/generate")
async def generate(
    prompt: str = Form(...),
    image: UploadFile = File(...),
    duration_seconds: Optional[float] = Form(None),
    num_frames: Optional[int] = Form(None),
    width: Optional[int] = Form(None),
    height: Optional[int] = Form(None),
    seed: Optional[int] = Form(None),
    negative_prompt: Optional[str] = Form(None),
):
    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty",
        )

    # ---------------------------------------------------------
    # Frames
    # ---------------------------------------------------------

    if num_frames is not None:
        requested = max(5, num_frames)
        frames = round((requested - 1) / 4) * 4 + 1

    elif duration_seconds is not None:
        frames = nearest_valid_frames(duration_seconds, int(cfg["fps"]))

    else:
        frames = int(cfg["num_frames"])

    # ---------------------------------------------------------
    # Other settings
    # ---------------------------------------------------------

    job_width = width if width is not None else cfg["width"]
    job_height = height if height is not None else cfg["height"]
    job_negative_prompt = (
        negative_prompt if negative_prompt is not None else cfg["negative_prompt"]
    )

    # ---------------------------------------------------------
    # Create job
    # ---------------------------------------------------------

    job_id = str(uuid.uuid4())

    with _jobs_lock:
        _jobs[job_id] = JobState()

    thread = threading.Thread(
        target=_run_job,
        args=(
            job_id,
            prompt,
            image_bytes,
            frames,
            job_width,
            job_height,
            seed,
            job_negative_prompt,
        ),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "num_frames": frames,
        "fps": cfg["fps"],
        "duration_seconds": round(frames / cfg["fps"], 2),
        "width": job_width,
        "height": job_height,
        "seed": seed,
    }


# ─────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────

@app.get("/status/{job_id}")
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    return {
        "job_id": job_id,
        "status": job.status,
        "error": job.error,
    }


# ─────────────────────────────────────────────────────────────
# Download
# ─────────────────────────────────────────────────────────────

@app.get("/download/{job_id}")
def download(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Job not done (status={job.status})",
        )

    video_path = job.video_path

    if video_path is None or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"wan22_i2v_{job_id}.mp4",
    )


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
