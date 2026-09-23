"""
backend/open_router/video.py — Image-to-video generation via OpenRouter's Videos API.

OpenRouter's video generation is asynchronous (submit -> poll -> download). This
module hides that lifecycle behind a single synchronous-looking call, mirroring
how tasks.py's _run_runpod_animation() already does inline submit/poll/download
against the self-hosted RunPod server.
"""

import base64
import mimetypes
import time
from pathlib import Path

from . import client, models


def generate_video(
    image_path: Path,
    prompt: str,
    api_key: str,
    duration_seconds: int = 5,
    model: str = models.VIDEO_MODEL,
    poll_interval: float = 5.0,
    max_wait_seconds: float = 600.0,
) -> bytes:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    data_uri = f"data:{mime_type};base64,{base64.b64encode(image_path.read_bytes()).decode()}"

    submit_resp = client.post(
        "/videos",
        api_key,
        json={
            "model": model,
            "prompt": prompt,
            "duration": duration_seconds,
            "frame_images": [
                {"type": "image_url", "image_url": {"url": data_uri}, "frame_type": "first_frame"}
            ],
        },
        timeout=30,
    )
    job = submit_resp.json()
    job_id = job["id"]
    polling_url = job["polling_url"]

    status = job.get("status", "pending")
    waited = 0.0
    result = job
    while status not in ("completed", "failed", "cancelled", "expired"):
        if waited >= max_wait_seconds:
            raise TimeoutError(f"OpenRouter video generation timed out after {max_wait_seconds}s (job {job_id})")
        time.sleep(poll_interval)
        waited += poll_interval
        result = client.get(polling_url, api_key, absolute=True, timeout=30).json()
        status = result.get("status")

    if status != "completed":
        raise RuntimeError(f"OpenRouter video generation failed (job {job_id}): {result.get('error')}")

    unsigned_urls = result.get("unsigned_urls") or []
    content_url = unsigned_urls[0] if unsigned_urls else f"{models.BASE_URL}/videos/{job_id}/content?index=0"

    content_resp = client.get(content_url, api_key, absolute=True, timeout=120)
    return content_resp.content
