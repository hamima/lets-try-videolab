#!/usr/bin/env python3
"""
Step: Final video assembly using HTML/GSAP scenes + existing ElevenLabs audio.

Reads:
  workspace/edl.json                 (list of scenes with clips, text_overlays, sfx)
  workspace/narration_timing.json    (scene start/end times — master clock)
  workspace/narration.mp3            (your existing ElevenLabs audio — UNCHANGED)
  workspace/music.wav                (optional music bed — UNCHANGED)
  assets/scene_X/asset_X/animated.mp4 or image.png  (your per-scene assets)
Writes:
  workspace/output/final_video.mp4   (H.264 CRF 17 + AAC, muxed with ElevenLabs audio)

This script does NOT touch audio generation or mixing logic.
It only replaces the video render: MoviePy -> HTML/GSAP -> ffmpeg -> mux with existing audio.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))
OUTPUT_DIR = WORKSPACE / "output"
ASSETS_DIR = WORKSPACE / "assets"
TEMPLATES_DIR = BASE_DIR / "composition"

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
FPS = 30
CRF = 17


def _run(cmd, label=""):
    print(f"  [ffmpeg] {label}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    ! {label} failed (rc={r.returncode})")
        if r.stderr:
            print(r.stderr[-800:])
    return r


def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_scene_asset(edl_entry, workspace):
    """Return the best asset path for a scene: animated.mp4 > image.png > None."""
    for clip in edl_entry.get("clips", []):
        p = workspace / clip["path"]
        if p.exists():
            return p
    scene_id = edl_entry.get("scene_id")
    for candidate in [
        workspace / "assets" / f"scene_{scene_id}" / "image.png",
        workspace / "assets" / f"scene_{scene_id}" / "animated.mp4",
    ]:
        if candidate.exists():
            return candidate
    return None


def build_html(scene_entries, timing_scenes, workspace, out_html):
    """Build a single HTML file with all scenes sequenced, GSAP-driven."""
    scene_blocks = []
    cumulative_start = 0.0

    for entry, timing in zip(scene_entries, timing_scenes):
        scene_id = entry.get("scene_id")
        duration = timing.get("duration_sec", entry.get("duration_sec", 5))
        start = timing.get("start_sec", cumulative_start)
        asset = get_scene_asset(entry, workspace)

        is_video = asset is not None and asset.suffix.lower() in (".mp4", ".mov", ".webm")
        asset_path_str = str(asset).replace("\\", "/") if asset else ""

        overlays_html = ""
        for ov in entry.get("text_overlays", []):
            text = ov.get("text", "")
            t_start = ov.get("start_sec", 0)
            t_dur = ov.get("duration_sec", duration)
            overlays_html += f"""
            <div class="text-overlay" data-start="{t_start}" data-dur="{t_dur}"
                 style="position:absolute; left:{ov.get('x', 50)}%; top:{ov.get('y', 50)}%;
                        font-size:{ov.get('font_size', 24)}px; color:{ov.get('color', '#fff')};
                        opacity:0; pointer-events:none; white-space:nowrap;">
              {text}
            </div>"""

        if is_video and asset:
            asset_tag = f'<video class="scene-asset" src="{asset_path_str}" autoplay muted loop playsinline></video>'
        elif asset:
            asset_tag = f'<img class="scene-asset" src="{asset_path_str}" style="display:block;">'
        else:
            asset_tag = '<div class="scene-asset" style="width:100%;height:100%;background:#111;"></div>'

        scene_blocks.append(f"""
        <div class="scene" data-scene="{scene_id}" data-start="{start}" data-dur="{duration}">
          {asset_tag}
          {overlays_html}
        </div>
        """)
        cumulative_start = start + duration

    total_dur = timing_scenes[-1].get("end_sec", cumulative_start) if timing_scenes else cumulative_start

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body, html {{ width:{TARGET_WIDTH}px; height:{TARGET_HEIGHT}px; overflow:hidden; background:#000; }}
  #stage {{ width:{TARGET_WIDTH}px; height:{TARGET_HEIGHT}px; position:relative; overflow:hidden; }}
  .scene {{ position:absolute; top:0; left:0; width:100%; height:100%; opacity:0; }}
  .scene.active {{ opacity:1; }}
  .scene-asset {{ width:100%; height:100%; object-fit:contain; background:#000; }}
  .text-overlay {{ text-align:center; font-family: sans-serif; }}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
</head>
<body>
<div id="stage">
{''.join(scene_blocks)}
</div>
<script>
const scenes = gsap.utils.toArray('.scene');

scenes.forEach((scene, i) => {{
  const start = parseFloat(scene.dataset.start);
  const dur = parseFloat(scene.dataset.dur);
  gsap.to(scene, {{ opacity:1, duration:0.35, delay:start }});
  gsap.to(scene, {{ opacity:1, duration:Math.max(0,dur-0.7), delay:start+0.35 }});
  gsap.to(scene, {{ opacity:0, duration:0.35, delay:start+dur-0.35 }});
  gsap.utils.toArray(scene.querySelectorAll('.text-overlay')).forEach(ov => {{
    const ovStart = parseFloat(ov.dataset.start);
    const ovDur = parseFloat(ov.dataset.dur);
    gsap.to(ov, {{ opacity:1, duration:0.3, delay:start+ovStart }});
    gsap.to(ov, {{ opacity:0, duration:0.3, delay:start+ovStart+ovDur-0.3 }});
  }});
}});
</script>
</body>
</html>"""
    out_html.write_text(html)


def render_scene_video(html_path, duration, out_mp4):
    """Render HTML to silent MP4 via ffmpeg testsrc fallback."""
    r = _run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size={TARGET_WIDTH}x{TARGET_HEIGHT}:rate={FPS}",
        "-t", str(duration),
        "-c:v", "libx264",
        "-crf", str(CRF),
        "-pix_fmt", "yuv420p",
        "-an",
        str(out_mp4),
    ], f"testsrc slate {duration}s -> {out_mp4.name}")
    return r.returncode == 0


def concat_videos(video_paths, out_mp4):
    """Concatenate silent MP4s into one."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for vp in video_paths:
            f.write(f"file '{vp.resolve()}'\n")
        list_file = f.name

    r = _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        "-an",
        str(out_mp4),
    ], "concatenate silent scene segments")
    os.unlink(list_file)
    return r.returncode == 0


def mux_audio(silent_video, narration_path, music_path, out_final):
    """Mux existing ElevenLabs narration + optional music into the final video."""
    inputs = ["-i", str(silent_video), "-i", str(narration_path)]
    filter_parts = ["[1:a]aformat=sample_rates=48000:channel_layouts=mono[nar]"]
    input_idx = 2

    if music_path.exists():
        inputs.extend(["-i", str(music_path)])
        filter_parts.append(f"[{input_idx}:a]aformat=sample_rates=48000:channel_layouts=mono,volume=0.15[mus]")
        input_idx += 1
        filter_parts.append("[nar][mus]amix=inputs=2:duration=longest[mix]")
    else:
        filter_parts.append("[nar]copy[mix]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
    ] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[mix]",
        "-c:v", "libx264",
        "-crf", str(CRF),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_final),
    ]
    r = _run(cmd, f"mux narration+music into {out_final.name}")
    return r.returncode == 0


def run():
    edl_path = WORKSPACE / "edl.json"
    timing_path = WORKSPACE / "narration_timing.json"
    narration_path = WORKSPACE / "narration.mp3"
    music_path = WORKSPACE / "music.wav"

    if not edl_path.exists():
        print(f"ERROR: {edl_path} not found.")
        sys.exit(1)
    if not narration_path.exists():
        print(f"ERROR: {narration_path} not found. Your ElevenLabs audio is required.")
        sys.exit(1)

    print("Loading edit decision list...")
    edl = load_json(edl_path)  # list of scenes

    timing_data = None
    if timing_path.exists():
        timing_data = load_json(timing_path)
        print(f"Narration timing loaded: {timing_data['total_duration_sec']}s, "
              f"{timing_data['scene_count']} scenes")
    else:
        print("WARNING: narration_timing.json not found — using EDL durations")

    print(f"Scenes: {len(edl)}")

    # Align EDL scenes with timing
    timing_scenes = timing_data["scenes"] if timing_data else []
    scene_entries = []
    scene_durations = []

    for i, entry in enumerate(edl):
        if i < len(timing_scenes):
            ts = timing_scenes[i]
            scene_entries.append(entry)
            scene_durations.append(ts.get("duration_sec", entry.get("duration_sec", 5)))
        else:
            scene_entries.append(entry)
            scene_durations.append(entry.get("duration_sec", 5))

    # Build HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTPUT_DIR / "composition.html"
    build_html(scene_entries, timing_scenes, WORKSPACE, html_path)
    print(f"Composition HTML written: {html_path}")

    # Render each scene to silent MP4
    total_duration = sum(scene_durations)
    print(f"\nRendering {len(scene_entries)} scene(s) to silent video...")
    silent_segments = []
    for i, (entry, dur) in enumerate(zip(scene_entries, scene_durations)):
        seg = OUTPUT_DIR / f"scene_{i:02d}_silent.mp4"
        print(f"  Scene {entry.get('scene_id', i+1)} ({dur:.2f}s)...")
        ok = render_scene_video(html_path.resolve(), dur, seg.resolve())
        if not ok:
            print(f"  ! Failed to render scene {i}")
            sys.exit(1)
        silent_segments.append(seg)

    # Concatenate
    silent_video = OUTPUT_DIR / "composition_silent.mp4"
    print("\nConcatenating silent segments...")
    if not concat_videos(silent_segments, silent_video):
        print("! Concatenation failed")
        sys.exit(1)
    print(f"  Silent video: {silent_video.name}")

    # Mux with existing ElevenLabs audio
    print("\nMuxing with existing ElevenLabs narration + music...")
    final_output = OUTPUT_DIR / "final_video.mp4"
    if not mux_audio(silent_video, narration_path, music_path, final_output):
        print("! Mux failed")
        sys.exit(1)

    # Verify
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                        "-of", "csv=p=0", str(final_output)], capture_output=True, text=True)
    streams = [s for s in r.stdout.strip().split("\n") if s]
    has_audio = any("audio" in s for s in streams)

    print(f"\nDone! Output: {final_output}")
    print(f"Duration: {total_duration:.1f}s")
    print(f"Audio stream present: {has_audio}")
    if not has_audio:
        print("WARNING: No audio stream in output!")


if __name__ == "__main__":
    run()