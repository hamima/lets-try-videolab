#!/usr/bin/env python3
"""
Step 18: Subtitles — generates subtitle.md from the narration's timing (via
ElevenLabs character-level alignment when available, falling back to
narration_timing.json's scene/pause data otherwise — see backend/subtitles.py
for the actual chunking logic) and burns the resulting captions into the
already-assembled output/final_video.mp4, overwriting it in place. Re-running
step 17 (Final Assembly) regenerates a clean, caption-free copy if ever needed.

Reads:  workspace/narration_script.txt
        workspace/narration_timing.json
        workspace/narration_alignment.json (optional — enables the primary,
            character-level path; its absence falls back to the pause
            heuristic, e.g. for OpenRouter TTS or a pre-existing older run)
        workspace/output/final_video.mp4
        fonts/NotoSansDevanagari-Bold.ttf (via text_overlay.py)
Writes: workspace/subtitle.md
        workspace/output/final_video.mp4 (overwritten in place)

Usage:
    python scripts/generate_subtitles.py
"""

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
# WORKSPACE_DIR is set by backend/tasks.py's _run_script() to the per-run workspace
# (workspace/<user>/<domain>/<run_id>); fall back to the repo-root workspace/ for
# standalone use.
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))
OUTPUT_DIR = WORKSPACE / "output"

# backend/subtitles.py holds the pure chunking/parsing logic (unit-tested in
# backend/tests/) — same sys.path convention scripts/migrate_workspaces_to_users.py
# already uses for backend/workspace_migration.py.
sys.path.insert(0, str(BASE_DIR / "backend"))
from subtitles import (  # noqa: E402
    chunk_from_alignment,
    chunk_from_scene_timing,
    extract_scene_texts,
    serialize_subtitles,
)

# text_overlay.py is the rendering code shared with assemble.py (step 17).
sys.path.insert(0, str(Path(__file__).parent))
from text_overlay import render_text_overlay  # noqa: E402

try:
    from moviepy import VideoFileClip, ImageClip, CompositeVideoClip
except ImportError:
    print("MoviePy not found. Install with: pip install moviepy")
    print("Also ensure ffmpeg is installed: brew install ffmpeg")
    sys.exit(1)


def load_captions() -> list[dict]:
    narration_timing = json.loads((WORKSPACE / "narration_timing.json").read_text())

    alignment_path = WORKSPACE / "narration_alignment.json"
    if alignment_path.exists():
        print("[generate_subtitles] Using ElevenLabs character-level alignment (primary path)")
        alignment = json.loads(alignment_path.read_text())
        return chunk_from_alignment(alignment, narration_timing)

    print("[generate_subtitles] No narration_alignment.json found — falling back to pause-heuristic timing")
    narration_script = (WORKSPACE / "narration_script.txt").read_text()
    scene_texts = extract_scene_texts(narration_script)
    return chunk_from_scene_timing(narration_timing, scene_texts)


def burn_captions(captions: list[dict]) -> None:
    video_path = OUTPUT_DIR / "final_video.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"{video_path} not found — run step 17 (Final Assembly) first")

    clip = VideoFileClip(str(video_path))
    frame_size = clip.size

    caption_clips = []
    for cap in captions:
        duration = cap["end_sec"] - cap["start_sec"]
        if duration <= 0 or not cap["text"]:
            continue
        frame = render_text_overlay(cap["text"], "subtitle", frame_size)
        txt_clip = ImageClip(frame).with_duration(duration).with_start(cap["start_sec"])
        caption_clips.append(txt_clip)

    if not caption_clips:
        print("[generate_subtitles] No captions to burn in — leaving final_video.mp4 unchanged")
        clip.close()
        return

    composed = CompositeVideoClip([clip] + caption_clips, size=frame_size)

    # Write to a temp file first, then atomically replace — a failed/interrupted
    # render must never leave final_video.mp4 truncated or corrupted.
    tmp_path = OUTPUT_DIR / "final_video.subtitled.tmp.mp4"
    try:
        composed.write_videofile(
            str(tmp_path),
            fps=clip.fps or 30,
            codec="libx264",
            audio_codec="aac",
            bitrate="8000k",
            preset="medium",
            threads=4,
        )
    finally:
        composed.close()
        clip.close()

    tmp_path.replace(video_path)
    print(f"[generate_subtitles] Burned {len(caption_clips)} caption(s) into {video_path}")


def main() -> None:
    captions = load_captions()
    (WORKSPACE / "subtitle.md").write_text(serialize_subtitles(captions))
    print(f"[generate_subtitles] Wrote subtitle.md with {len(captions)} caption(s)")
    burn_captions(captions)


if __name__ == "__main__":
    main()
