"""
backend/ken_burns.py — Python/MoviePy Ken-Burns renderer for ai_image assets
that are not animated by an AI video model. Produces animated.mp4 directly
from a still image.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from moviepy import ImageClip, VideoClip

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
FPS = 30


def _resize_to_fill(clip, target_w: int, target_h: int):
    clip_aspect = clip.w / clip.h
    target_aspect = target_w / target_h
    if clip_aspect > target_aspect:
        new_height = target_h
        new_width = int(clip_aspect * target_h)
    else:
        new_width = target_w
        new_height = int(target_w / clip_aspect)
    clip = clip.resized((new_width, new_height))
    x_center = new_width // 2
    y_center = new_height // 2
    clip = clip.cropped(
        x1=x_center - target_w // 2,
        y1=y_center - target_h // 2,
        x2=x_center + target_w // 2,
        y2=y_center + target_h // 2,
    )
    return clip


def _zoom_frame_function(base_image: Image.Image, width: int, height: int, intensity: float, duration_seconds: float, zoom_in: bool):
    """Crop a shrinking/growing window out of an oversized base image and
    resize it back to (width, height) every frame, so the clip's output
    frame size never changes (required for MoviePy/ffmpeg to encode).
    """
    oversized_w, oversized_h = base_image.size

    def get_frame(t):
        progress = min(max(t / duration_seconds, 0.0), 1.0)
        scale = (1.0 + intensity * (1.0 - progress)) if zoom_in else (1.0 + intensity * progress)
        window_w = width * scale
        window_h = height * scale
        x1 = int(round((oversized_w - window_w) / 2))
        y1 = int(round((oversized_h - window_h) / 2))
        window = base_image.crop((x1, y1, x1 + round(window_w), y1 + round(window_h)))
        window = window.resize((width, height), Image.Resampling.LANCZOS)
        return np.array(window)

    return get_frame


def _pan_frame_function(base_image: Image.Image, width: int, height: int, duration_seconds: float, pan_right: bool):
    """Crop a fixed-size (width, height) window that slides horizontally
    across an oversized base image.
    """
    oversized_w, oversized_h = base_image.size
    max_shift = oversized_w - width
    y1 = int(round((oversized_h - height) / 2))

    def get_frame(t):
        progress = min(max(t / duration_seconds, 0.0), 1.0)
        x1 = int(round(max_shift * progress)) if pan_right else int(round(max_shift * (1.0 - progress)))
        window = base_image.crop((x1, y1, x1 + width, y1 + height))
        return np.array(window)

    return get_frame


def render_ken_burns(
    image_path: Path,
    out_path: Path,
    direction: str,
    intensity: float,
    duration_seconds: float,
    width: int = TARGET_WIDTH,
    height: int = TARGET_HEIGHT,
) -> Path:
    """Render a Ken-Burns zoom/pan clip from a static image.

    direction: one of "zoom_in", "zoom_out", "pan_left", "pan_right".
    intensity: 0.1-0.3, how strong the zoom/pan motion is.
    """
    oversized_w = int(round(width * (1.0 + intensity)))
    oversized_h = int(round(height * (1.0 + intensity)))

    source = ImageClip(str(image_path))
    source = _resize_to_fill(source, oversized_w, oversized_h)
    base_image = Image.fromarray(source.get_frame(0))

    if direction == "zoom_in":
        frame_function = _zoom_frame_function(base_image, width, height, intensity, duration_seconds, zoom_in=True)
    elif direction == "zoom_out":
        frame_function = _zoom_frame_function(base_image, width, height, intensity, duration_seconds, zoom_in=False)
    elif direction == "pan_left":
        frame_function = _pan_frame_function(base_image, width, height, duration_seconds, pan_right=False)
    elif direction == "pan_right":
        frame_function = _pan_frame_function(base_image, width, height, duration_seconds, pan_right=True)
    else:
        center_x1 = int(round((oversized_w - width) / 2))
        center_y1 = int(round((oversized_h - height) / 2))
        static_frame = np.array(base_image.crop((center_x1, center_y1, center_x1 + width, center_y1 + height)))
        frame_function = lambda t: static_frame

    clip = VideoClip(frame_function, duration=duration_seconds)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    clip.write_videofile(str(out_path), fps=FPS, codec="libx264", audio=False, logger=None)
    return out_path
