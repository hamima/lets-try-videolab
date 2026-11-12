#!/usr/bin/env python3
"""
Step 4: Render — HTML/GSAP scenes → silent MP4 → mux with soundtrack.

Pipeline:
  hyperframes (preferred) → Playwright frame capture → ffmpeg testsrc (fallback)

Reads:
  composition/render_order.json   (ordered scenes + durations)
  composition/scene_NN.html       (per-scene GSAP composition)
  composition/audio/soundtrack.wav (mixed+mastered audio)

Writes:
  output/final_video.mp4          (H.264 CRF ~17, AAC audio)

Usage:
    python scripts/render.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = BASE_DIR / "composition"
AUDIO_DIR = COMPOSITION_DIR / "audio"
RENDER_ORDER_PATH = COMPOSITION_DIR / "render_order.json"
SOUNDTRACK_PATH = AUDIO_DIR / "soundtrack.wav"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_PATH = OUTPUT_DIR / "final_video.mp4"

FPS = 30
W, H = 1920, 1080
CRF = 17


def _load_render_order():
    return json.loads(RENDER_ORDER_PATH.read_text())


def _ffprobe_duration(path):
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "csv=p=0", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return float(r.stdout.strip()) if r.stdout.strip() else 0.0


def _run(cmd, label):
    print(f"  [ffmpeg] {label}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2500:])
        raise SystemExit(f"ffmpeg failed: {label}")
    return r


def _render_testsrc(out_path, duration):
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"testsrc=duration={duration}:size={W}x{H}:rate={FPS}",
        "-an",
        "-c:v", "libx264", "-crf", str(CRF), "-preset", "medium",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    _run(cmd, f"testsrc slate {duration:.2f}s → {out_path.name}")


def _render_playwright(html_path, out_path, duration):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright not installed (pip install playwright)")

    total_frames = int(round(duration * FPS))
    frame_time_ms = 1000.0 / FPS

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(f"file://{html_path}", wait_until="networkidle")
        page.wait_for_timeout(800)

        tmpdir = Path(tempfile.mkdtemp(prefix="frames_"))
        try:
            for i in range(total_frames):
                page.wait_for_timeout(frame_time_ms)
                page.screenshot(path=str(tmpdir / f"{i:06d}.png"))

            cmd = [
                "ffmpeg", "-y",
                "-framerate", str(FPS),
                "-i", str(tmpdir / "%06d.png"),
                "-an",
                "-c:v", "libx264", "-crf", str(CRF), "-preset", "medium",
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(out_path),
            ]
            _run(cmd, f"Playwright capture {total_frames} frames → {out_path.name}")
        finally:
            browser.close()
            shutil.rmtree(tmpdir, ignore_errors=True)

def _render_hyperframes(html_path, out_path, duration):
    npx = shutil.which("npx")
    if not npx:
        return False
    cmd = [
        "npx", "--yes", "hyperframes@latest",
        "--input", f"file://{html_path}",
        "--output", str(out_path),
        "--duration", str(duration),
        "--fps", str(FPS),
        "--width", str(W), "--height", str(H),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        print("  hyperframes timed out — falling back")
        return False
    if r.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
        print(f"  [hyperframes] rendered → {out_path.name}")
        return True
    print(f"  hyperframes failed (rc={r.returncode}): {(r.stderr or '')[-300:]}")
    return False


def render_scenes(render_order):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = []

    for entry in render_order:
        scene = entry["scene"]
        html_path = COMPOSITION_DIR / entry["file"]
        duration = entry["duration"]
        seg_path = OUTPUT_DIR / f"scene_{scene:02d}.mp4"

        print(f"\nRendering scene {scene} ({duration:.2f}s)...")

        if not _render_hyperframes(html_path, seg_path, duration):
            print("  hyperframes unavailable/failed — trying Playwright capture")
            try:
                _render_playwright(html_path, seg_path, duration)
            except SystemExit as e:
                print(f"  {e} — using ffmpeg testsrc fallback")
                _render_testsrc(seg_path, duration)

        segments.append(seg_path)

    concat_list = OUTPUT_DIR / "_segments.txt"
    with open(concat_list, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")

    silent_mp4 = OUTPUT_DIR / "silent_video.mp4"
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(silent_mp4),
    ]
    _run(cmd, "concatenate scene segments")
    concat_list.unlink(missing_ok=True)

    return silent_mp4


def mux_audio(silent_video):
    if not SOUNDTRACK_PATH.exists():
        print("⚠ No soundtrack found — exporting video without audio")
        shutil.copy(silent_video, OUTPUT_PATH)
        return OUTPUT_PATH

    video_dur = _ffprobe_duration(silent_video)
    audio_dur = _ffprobe_duration(SOUNDTRACK_PATH)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(silent_video),
        "-i", str(SOUNDTRACK_PATH),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0?",
        "-shortest",
        "-movflags", "+faststart",
        str(OUTPUT_PATH),
    ]
    _run(cmd, f"mux audio ({audio_dur:.2f}s) with video ({video_dur:.2f}s) CRF {CRF}")

    return OUTPUT_PATH


def run():
    if not RENDER_ORDER_PATH.exists():
        raise SystemExit("render_order.json not found — run scripts/compose.py first")

    render_order = _load_render_order()
    print(f"Rendering {len(render_order)} scene(s)...")
    silent_video = render_scenes(render_order)
    final = mux_audio(silent_video)

    final_dur = _ffprobe_duration(final)
    print(f"\n✓ Final video: {final} ({final_dur:.2f}s)")
    return final


if __name__ == "__main__":
    run()
