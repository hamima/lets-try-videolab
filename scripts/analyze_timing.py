#!/usr/bin/env python3
"""
Step 12b: Narration Timing Analysis


Analyzes narration.mp3 to extract:
- Per-scene start/end timestamps (using silence detection)
- Pause locations (for music swells)
- Total spoken duration per segment


This produces the TIMING TRUTH that the creative director and assembler use.


Reads:  workspace/narration.mp3
       workspace/narration_script.txt (to count scenes)
Writes: workspace/narration_timing.json


Usage:
   python scripts/analyze_timing.py
"""


import json
import os
import re
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
# WORKSPACE_DIR is set by backend/tasks.py's _run_script() to the per-run workspace
# (workspace/<domain>/<run_id>); fall back to the repo-root workspace/ for standalone use.
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))




def detect_silences(audio_path: Path, silence_thresh=-35, min_silence_ms=600):
   """Use ffmpeg silencedetect to find pauses in narration."""
   cmd = [
       "ffmpeg", "-i", str(audio_path),
       "-af", f"silencedetect=noise={silence_thresh}dB:d={min_silence_ms/1000}",
       "-f", "null", "-"
   ]
   result = subprocess.run(cmd, capture_output=True, text=True)
   output = result.stderr


   silences = []
   starts = re.findall(r"silence_start: ([\d.]+)", output)
   ends = re.findall(r"silence_end: ([\d.]+)", output)


   for s, e in zip(starts, ends):
       silences.append({
           "start": round(float(s), 2),
           "end": round(float(e), 2),
           "duration": round(float(e) - float(s), 2)
       })


   return silences




def get_audio_duration(audio_path: Path):
   cmd = [
       "ffprobe", "-v", "quiet",
       "-show_entries", "format=duration",
       "-of", "csv=p=0", str(audio_path)
   ]
   result = subprocess.run(cmd, capture_output=True, text=True)
   return round(float(result.stdout.strip()), 2)




def count_scenes_from_script(script_path: Path):
   """Count scenes from the reference version of narration script."""
   if not script_path.exists():
       return 0
   text = script_path.read_text()
   return len(re.findall(r"\[SCENE \d+\]", text))




def assign_scenes_to_silences(silences, total_duration, scene_count):
   """
   Use silences as scene boundaries. Prefers silences >= 1.2s (explicit breaks),
   but falls back to the top N longest silences if not enough long ones exist.
   """
   needed = scene_count - 1


   # Prefer long silences as explicit scene breaks
   scene_breaks = sorted(
       [s for s in silences if s["duration"] >= 1.2],
       key=lambda x: x["duration"],
       reverse=True
   )[:needed]


   # Fallback: not enough long silences — use the longest available
   if len(scene_breaks) < needed:
       scene_breaks = sorted(
           silences,
           key=lambda x: x["duration"],
           reverse=True
       )[:needed]


   # If still not enough silences for all scenes, distribute remaining evenly
   if len(scene_breaks) < needed:
       # Use all available silences as boundaries, then subdivide the longest
       # resulting segments to fill the remaining scene slots
       existing_breaks = sorted(scene_breaks, key=lambda x: x["start"])
       boundaries = [0.0] + [round((s["start"] + s["end"]) / 2, 2) for s in existing_breaks] + [total_duration]


       while len(boundaries) - 1 < scene_count:
           # Find the longest segment and split it in half
           max_gap = 0
           max_idx = 0
           for idx in range(len(boundaries) - 1):
               gap = boundaries[idx + 1] - boundaries[idx]
               if gap > max_gap:
                   max_gap = gap
                   max_idx = idx
           mid = round((boundaries[max_idx] + boundaries[max_idx + 1]) / 2, 2)
           boundaries.insert(max_idx + 1, mid)


       scenes = []
       for i in range(scene_count):
           scenes.append({
               "scene_id": i + 1,
               "start_sec": round(boundaries[i], 2),
               "end_sec": round(boundaries[i + 1], 2),
               "duration_sec": round(boundaries[i + 1] - boundaries[i], 2)
           })
       return scenes


   # Sort by time position
   scene_breaks = sorted(scene_breaks, key=lambda x: x["start"])


   # Build scene timing
   scenes = []
   prev_end = 0.0


   for i in range(scene_count):
       scene_start = prev_end


       if i < len(scene_breaks):
           # Scene ends at the midpoint of the silence
           silence = scene_breaks[i]
           scene_end = round((silence["start"] + silence["end"]) / 2, 2)
           prev_end = scene_end
       else:
           scene_end = total_duration


       scenes.append({
           "scene_id": i + 1,
           "start_sec": round(scene_start, 2),
           "end_sec": round(scene_end, 2),
           "duration_sec": round(scene_end - scene_start, 2)
       })


   return scenes




def find_emphasis_pauses(silences, scene_timing):
   """Find shorter pauses within scenes — these are emphasis/breathing moments."""
   for scene in scene_timing:
       internal_pauses = [
           s for s in silences
           if s["start"] >= scene["start_sec"]
           and s["end"] <= scene["end_sec"]
           and s["duration"] < 1.2
           and s["duration"] >= 0.4
       ]
       scene["internal_pauses"] = internal_pauses
       scene["pause_count"] = len(internal_pauses)


   return scene_timing




def find_music_moments(silences, scene_timing):
   """Identify moments where music can swell (long pauses between scenes)."""
   music_swells = []
   for i in range(len(scene_timing) - 1):
       gap_start = scene_timing[i]["end_sec"]
       gap_end = scene_timing[i + 1]["start_sec"]
       if gap_end - gap_start >= 0.5:
           music_swells.append({
               "between_scenes": [i + 1, i + 2],
               "start_sec": round(gap_start, 2),
               "end_sec": round(gap_end, 2),
               "duration_sec": round(gap_end - gap_start, 2),
               "suggestion": "music_swell"
           })


   return music_swells




def run():
   narration_path = WORKSPACE / "narration.mp3"
   script_path = WORKSPACE / "narration_script.txt"
   output_path = WORKSPACE / "narration_timing.json"


   if not narration_path.exists():
       print(f"ERROR: {narration_path} not found")
       sys.exit(1)


   print("Analyzing narration timing...")


   # Get total duration
   total_duration = get_audio_duration(narration_path)
   print(f"  Total duration: {total_duration}s")


   # Detect silences
   silences = detect_silences(narration_path)
   print(f"  Detected {len(silences)} silence segments")


   # Count scenes
   scene_count = count_scenes_from_script(script_path)
   if scene_count == 0:
       # Fallback: estimate from scene_plan.md
       plan_path = WORKSPACE / "scene_plan.md"
       if plan_path.exists():
           scene_count = len(re.findall(r"^SCENE \d+", plan_path.read_text(), re.MULTILINE))
   print(f"  Scene count: {scene_count}")


   if scene_count == 0:
       print("ERROR: Cannot determine scene count")
       sys.exit(1)


   # Assign timing to scenes
   scene_timing = assign_scenes_to_silences(silences, total_duration, scene_count)


   # Find internal pauses (emphasis moments)
   scene_timing = find_emphasis_pauses(silences, scene_timing)


   # Find music swell opportunities
   music_swells = find_music_moments(silences, scene_timing)


   # Build output
   timing_data = {
       "total_duration_sec": total_duration,
       "scene_count": scene_count,
       "scenes": scene_timing,
       "music_swell_points": music_swells,
       "all_silences": silences
   }


   # Print summary
   print(f"\n  Scene Timing:")
   for s in scene_timing:
       print(f"    Scene {s['scene_id']:2d}: {s['start_sec']:6.2f}s – {s['end_sec']:6.2f}s "
             f"({s['duration_sec']:.1f}s) | {s['pause_count']} internal pauses")


   print(f"\n  Music swell opportunities: {len(music_swells)}")
   for m in music_swells:
       print(f"    Between scenes {m['between_scenes']}: {m['start_sec']}s – {m['end_sec']}s")


   # Save
   with open(output_path, "w") as f:
       json.dump(timing_data, f, indent=2)


   print(f"\n→ Saved to {output_path}")




if __name__ == "__main__":
   run()



