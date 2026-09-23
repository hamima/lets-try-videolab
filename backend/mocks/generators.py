"""
backend/mocks/generators.py — On-the-fly placeholder binary generators for mock mode.

Uses PIL (Pillow) for images and ffmpeg for audio/video.
Both are already required by the main pipeline, so no new dependencies.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def generate_placeholder_image(path: Path) -> None:
    """Write a 512x512 gray PNG with 'MOCK IMAGE' text to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (512, 512), color=(100, 100, 100))
        draw = ImageDraw.Draw(img)

        label = "MOCK IMAGE"
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=48)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((512 - w) // 2, (512 - h) // 2), label, fill=(220, 220, 220), font=font)

        img.save(str(path), format="PNG" if str(path).endswith(".png") else "JPEG")

    except ImportError:
        # Minimal valid 1x1 gray PNG as absolute fallback
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x00"
            b"\x00\x00\x00:~\x9bU\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x00"
            b"\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def generate_silent_audio(path: Path, duration_seconds: float = 10.0, fmt: str = "mp3") -> None:
    """Write a silent audio file (mp3 or wav) of *duration_seconds* to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-t", str(duration_seconds),
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def generate_placeholder_video(path: Path, duration_seconds: float = 5.0) -> None:
    """Write a black 1280x720 MP4 at 16 fps of *duration_seconds* to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:size=1280x720:r=16",
            "-t", str(duration_seconds),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
