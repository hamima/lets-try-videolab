"""
backend/tests/test_ken_burns.py — Smoke test for backend/ken_burns.py's
render_ken_burns(), which renders a Ken-Burns zoom/pan clip from a static
image using MoviePy. This is pipeline glue code, not pixel-accuracy-critical
logic, so we only verify the output file exists, is non-empty, and has
roughly the expected duration.
"""

from pathlib import Path

import pytest
from PIL import Image

from ken_burns import render_ken_burns


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "source.png"
    Image.new("RGB", (640, 360), color=(120, 160, 200)).save(image_path)
    return image_path


@pytest.mark.parametrize("direction", ["zoom_in", "zoom_out", "pan_left", "pan_right"])
def test_render_ken_burns_produces_video(tmp_path: Path, sample_image: Path, direction: str):
    out_path = tmp_path / "animated.mp4"
    duration_seconds = 1.0

    result = render_ken_burns(
        sample_image, out_path, direction, intensity=0.2, duration_seconds=duration_seconds,
        width=320, height=180,
    )

    assert result == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0
