import gc
import io
import threading
from pathlib import Path
from typing import Optional

import torch
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
from diffusers.utils import export_to_video
from PIL import Image


# ─────────────────────────────────────────────────────────────
# Pipeline (module-level singleton, internal)
# ─────────────────────────────────────────────────────────────

_pipe = None
_pipe_lock = threading.Lock()


def _clear_gpu():
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def _configure_memory(pipe, memory_mode: str):
    if memory_mode == "cpu_offload":
        print("[model] CPU offload enabled")
        pipe.enable_model_cpu_offload()

    elif memory_mode == "cuda":
        print("[model] Moving pipeline to CUDA")
        pipe.to("cuda")

    else:
        raise ValueError(f"Unknown memory_mode: {memory_mode}")


def _load_pipeline(model_id: str, memory_mode: str):
    global _pipe

    if _pipe is not None:
        return _pipe

    print(f"[model] Loading I2V: {model_id}")

    vae = AutoencoderKLWan.from_pretrained(
        model_id,
        subfolder="vae",
        torch_dtype=torch.float32,
    )

    _pipe = WanImageToVideoPipeline.from_pretrained(
        model_id,
        vae=vae,
        torch_dtype=torch.bfloat16,
    )

    _configure_memory(_pipe, memory_mode)

    print("[model] I2V pipeline ready")

    return _pipe


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def nearest_valid_frames(duration_seconds: float, fps: int) -> int:
    """
    Wan video frame counts should follow:

        num_frames = 4n + 1

    Convert desired duration to the nearest valid count.
    """
    target = max(5, round(duration_seconds * fps))
    n = round((target - 1) / 4)
    return max(5, 4 * n + 1)


def run_inference(
    job_id: str,
    prompt: str,
    image_bytes: bytes,
    num_frames: int,
    width: int,
    height: int,
    seed: Optional[int],
    negative_prompt: str,
    output_dir: Path,
    num_inference_steps: int,
    guidance_scale: float,
    guidance_scale_2: float,
    model_id: str,
    memory_mode: str,
    fps: int,
) -> Path:
    """
    Run Wan I2V inference. Returns the output video path on success,
    or raises an exception on failure. Does not mutate any job state.
    """
    try:
        with _pipe_lock:
            pipe = _load_pipeline(model_id, memory_mode)

            generator = None

            if seed is not None:
                generator = torch.Generator(device="cuda").manual_seed(seed)

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

            print(
                f"[job {job_id}] "
                f"I2V {width}x{height}, "
                f"{num_frames} frames"
            )

            call_args = {
                "image": image,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_frames": num_frames,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "guidance_scale_2": guidance_scale_2,
            }

            if generator is not None:
                call_args["generator"] = generator

            result = pipe(**call_args)
            frames = result.frames[0]

            out_path = output_dir / f"{job_id}.mp4"

            export_to_video(frames, str(out_path), fps=fps)

        print(f"[job {job_id}] DONE → {out_path}")

        return out_path

    except Exception:
        _clear_gpu()
        raise
