#!/usr/bin/env python3
"""
FastAPI server — LTX-Video I2V direct inference (no ComfyUI layer).

Endpoints:
  POST /generate          — submit image + prompt → {job_id}
  GET  /status/{job_id}   — poll job status
  GET  /download/{job_id} — stream video, then auto-delete
  GET  /config            — view current server config

Config:
  Reads server_config.json on startup (created with defaults if missing).
  Config file path: SERVER_CONFIG env var, or ./server_config.json next to this file.

Auto-shutdown:
  The server shuts itself down after `idle_timeout_minutes` of inactivity.
  "Inactive" means no HTTP requests AND no jobs currently running/pending.
  Set idle_timeout_minutes=0 to disable auto-shutdown.
"""

import io
import json
import os
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

import torch
import uvicorn
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

# ─────────────────────────────────────────────────────────────
# Config — loaded from JSON, created with defaults if missing
# ─────────────────────────────────────────────────────────────

_CONFIG_DEFAULTS: dict = {
    "model_id": "Lightricks/LTX-Video",
    "host": "0.0.0.0",
    "port": 8080,
    "idle_timeout_minutes": 30,
    "output_dir": "/tmp/ltx_outputs",
    "width": 704,
    "height": 480,
    "num_inference_steps": 30,
    "guidance_scale": 3.0,
}

_CONFIG_PATH = Path(os.environ.get("SERVER_CONFIG", Path(__file__).parent / "server_config.json"))


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        stored = json.loads(_CONFIG_PATH.read_text())
        return {**_CONFIG_DEFAULTS, **stored}
    _CONFIG_PATH.write_text(json.dumps(_CONFIG_DEFAULTS, indent=2))
    print(f"[config] Created default config at {_CONFIG_PATH}")
    return dict(_CONFIG_DEFAULTS)


cfg = _load_config()

if os.environ.get("LTX_MODEL_ID"):
    cfg["model_id"] = os.environ["LTX_MODEL_ID"]

print(f"[config] {cfg}")

# ─────────────────────────────────────────────────────────────
# Model — loaded once at startup, shared across all requests
# ─────────────────────────────────────────────────────────────

LTX_FPS = 24  # LTX-Video native output framerate


def _nearest_valid_frames(duration_seconds: int) -> int:
    """LTX-Video requires (num_frames - 1) % 8 == 0. Return nearest valid count."""
    target = duration_seconds * LTX_FPS
    n = round(target / 8) * 8 + 1
    return max(9, n)  # minimum 9 frames


print(f"[startup] Loading {cfg['model_id']} ...")
pipe = LTXImageToVideoPipeline.from_pretrained(
    cfg["model_id"],
    torch_dtype=torch.bfloat16,
)
pipe.to("cuda")
print("[startup] Model loaded — server ready")

# ─────────────────────────────────────────────────────────────
# Job state
# ─────────────────────────────────────────────────────────────

OUTPUT_DIR = Path(cfg["output_dir"])
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class JobState:
    def __init__(self) -> None:
        self.status: str = "pending"   # pending | processing | done | failed
        self.video_path: Optional[Path] = None
        self.error: Optional[str] = None


_jobs: Dict[str, JobState] = {}
_jobs_lock = threading.Lock()

# ─────────────────────────────────────────────────────────────
# Idle watchdog
# ─────────────────────────────────────────────────────────────

_last_activity: float = time.monotonic()
_activity_lock = threading.Lock()


def _touch_activity() -> None:
    global _last_activity
    with _activity_lock:
        _last_activity = time.monotonic()


def _has_active_jobs() -> bool:
    with _jobs_lock:
        return any(j.status in ("pending", "processing") for j in _jobs.values())


def _idle_watchdog() -> None:
    timeout = cfg["idle_timeout_minutes"]
    if timeout <= 0:
        return
    timeout_secs = timeout * 60
    check_interval = 60

    print(f"[watchdog] Auto-shutdown after {timeout} min of inactivity")
    while True:
        time.sleep(check_interval)
        with _activity_lock:
            idle_secs = time.monotonic() - _last_activity

        if idle_secs >= timeout_secs and not _has_active_jobs():
            print(f"[watchdog] Idle for {idle_secs / 60:.1f} min — shutting down")
            os.kill(os.getpid(), signal.SIGTERM)
            return


# ─────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────

app = FastAPI(title="LTX-Video I2V Server")


@app.middleware("http")
async def _track_activity(request: Request, call_next):
    _touch_activity()
    return await call_next(request)


@app.on_event("startup")
def _start_watchdog():
    t = threading.Thread(target=_idle_watchdog, daemon=True)
    t.start()


def _run_inference(job_id: str, image_bytes: bytes, prompt: str, num_frames: int) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "processing"

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        frames = pipe(
            image=image,
            prompt=prompt,
            num_frames=num_frames,
            width=cfg["width"],
            height=cfg["height"],
            num_inference_steps=cfg["num_inference_steps"],
            guidance_scale=cfg["guidance_scale"],
        ).frames[0]

        out_path = OUTPUT_DIR / f"{job_id}.mp4"
        export_to_video(frames, str(out_path), fps=LTX_FPS)

        with _jobs_lock:
            _jobs[job_id].status = "done"
            _jobs[job_id].video_path = out_path

    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id].status = "failed"
            _jobs[job_id].error = str(exc)
        print(f"[job {job_id}] FAILED: {exc}")


@app.get("/config")
def get_config():
    """View current server configuration."""
    idle = cfg["idle_timeout_minutes"]
    with _activity_lock:
        idle_secs = time.monotonic() - _last_activity
    return {
        **cfg,
        "config_path": str(_CONFIG_PATH),
        "idle_seconds": round(idle_secs),
        "auto_shutdown": idle > 0,
    }


@app.post("/generate")
async def generate(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    duration_seconds: int = Form(5),
):
    """Submit an image + prompt. Returns job_id immediately."""
    image_bytes = await image.read()
    num_frames = _nearest_valid_frames(duration_seconds)

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = JobState()

    thread = threading.Thread(
        target=_run_inference,
        args=(job_id, image_bytes, prompt, num_frames),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id}


@app.get("/status/{job_id}")
def status(job_id: str):
    """Poll job status."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"status": job.status, "error": job.error}


@app.get("/download/{job_id}")
def download(job_id: str):
    """Stream the finished video, then delete it."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    if job.status != "done":
        raise HTTPException(status_code=404, detail=f"Job not done (status={job.status})")

    video_path = job.video_path
    if video_path is None or not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file missing")

    def cleanup() -> None:
        try:
            video_path.unlink(missing_ok=True)
        except OSError:
            pass
        with _jobs_lock:
            _jobs.pop(job_id, None)

    from starlette.background import BackgroundTask
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename="animated.mp4",
        background=BackgroundTask(cleanup),
    )


if __name__ == "__main__":
    uvicorn.run(app, host=cfg["host"], port=cfg["port"])
