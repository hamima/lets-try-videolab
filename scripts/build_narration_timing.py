#!/usr/bin/env python3
"""
Step 12b: Build Narration Timing from Per-Scene Audio Files


Reads per-scene MP3 files, measures their exact durations, concatenates them
into a single narration.mp3, and writes narration_timing.json with perfect
per-scene timestamps.


Reads:  workspace/narration_scenes/scene_01.mp3 ... scene_NN.mp3
Writes: workspace/narration.mp3 (concatenated)
       workspace/narration_timing.json (timing data)


Usage:
   python scripts/build_narration_timing.py
"""


import json
import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
WORKSPACE = BASE_DIR / "workspace"
SCENES_DIR = WORKSPACE / "narration_scenes"




def get_audio_duration(audio_path: Path):
   """Get exact duration of an audio file via ffprobe."""
   cmd = [
       "ffprobe", "-v", "quiet",
       "-show_entries", "format=duration",
       "-of", "csv=p=0", str(audio_path)
   ]
   result = subprocess.run(cmd, capture_output=True, text=True)
   if result.returncode != 0 or not result.stdout.strip():
       return None
   return round(float(result.stdout.strip()), 3)




def detect_silences_in_file(audio_path: Path, silence_thresh=-35, min_silence_ms=400):
   """Detect silences within a single audio file for music ducking."""
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




def concatenate_audio_files(scene_paths, output_path):
   """Concatenate scene MP3s into a single narration file using ffmpeg."""
   list_file = WORKSPACE / "_concat_list.txt"
   with open(list_file, "w") as f:
       for path in scene_paths:
           f.write(f"file '{path}'\n")


   cmd = [
       "ffmpeg", "-y", "-f", "concat", "-safe", "0",
       "-i", str(list_file),
       "-c", "copy",
       str(output_path)
   ]
   result = subprocess.run(cmd, capture_output=True, text=True)
   list_file.unlink()


   if result.returncode != 0:
       print(f"  WARNING: ffmpeg concat failed, trying re-encode...")
       cmd = [
           "ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_file) if list_file.exists() else "/dev/null",
           "-acodec", "libmp3lame", "-q:a", "2",
           str(output_path)
       ]
       # Recreate list file and retry with re-encode
       with open(list_file, "w") as f:
           for path in scene_paths:
               f.write(f"file '{path}'\n")
       result = subprocess.run(cmd, capture_output=True, text=True)
       list_file.unlink(missing_ok=True)


   return result.returncode == 0




def run():
   print("Building narration timing from per-scene audio files...")


   # Find scene audio files
   scene_files = sorted(SCENES_DIR.glob("scene_*.mp3"))
   if not scene_files:
       print(f"ERROR: No scene_*.mp3 files found in {SCENES_DIR}")
       print(f"  Generate per-scene audio files first (run step 8b for text, then TTS each).")
       return


   scene_count = len(scene_files)
   print(f"  Found {scene_count} scene audio files")


   # Measure each scene's duration
   scenes = []
   cumulative_time = 0.0


   print(f"\n  Scene Timing:")
   for i, scene_path in enumerate(scene_files, 1):
       duration = get_audio_duration(scene_path)
       if duration is None:
           print(f"  ERROR: Cannot read duration of {scene_path.name}")
           return


       start = round(cumulative_time, 3)
       end = round(cumulative_time + duration, 3)


       # Detect internal silences for music ducking
       internal_silences = detect_silences_in_file(scene_path)
       # Offset silences to absolute timeline position
       for s in internal_silences:
           s["start"] = round(s["start"] + start, 2)
           s["end"] = round(s["end"] + start, 2)


       scene_data = {
           "scene_id": i,
           "start_sec": round(start, 2),
           "end_sec": round(end, 2),
           "duration_sec": round(duration, 2),
           "internal_pauses": internal_silences,
           "pause_count": len(internal_silences)
       }
       scenes.append(scene_data)
       cumulative_time = end


       print(f"    Scene {i:2d}: {start:6.2f}s – {end:6.2f}s "
             f"({duration:.2f}s) | {len(internal_silences)} pauses")


   total_duration = round(cumulative_time, 2)
   print(f"\n  Total duration: {total_duration}s")


   # Concatenate into single narration.mp3
   output_narration = WORKSPACE / "narration.mp3"
   print(f"\n  Concatenating → {output_narration.name}...")
   success = concatenate_audio_files(scene_files, output_narration)
   if success:
       actual_duration = get_audio_duration(output_narration)
       print(f"  Concatenated: {actual_duration}s")
   else:
       print(f"  WARNING: Concatenation may have failed")


   # Collect all silences for music ducking
   all_silences = []
   for scene in scenes:
       all_silences.extend(scene["internal_pauses"])


   # Find music swell opportunities (gaps between scenes where music can rise)
   music_swells = []
   for i in range(len(scenes) - 1):
       gap_start = scenes[i]["end_sec"]
       gap_end = scenes[i + 1]["start_sec"]
       if gap_end - gap_start >= 0.3:
           music_swells.append({
               "between_scenes": [i + 1, i + 2],
               "start_sec": gap_start,
               "end_sec": gap_end,
               "duration_sec": round(gap_end - gap_start, 2),
               "suggestion": "music_swell"
           })


   # Build output
   timing_data = {
       "total_duration_sec": total_duration,
       "scene_count": scene_count,
       "scenes": scenes,
       "music_swell_points": music_swells,
       "all_silences": all_silences
   }


   # Save
   output_path = WORKSPACE / "narration_timing.json"
   with open(output_path, "w") as f:
       json.dump(timing_data, f, indent=2)


   print(f"\n  Music swell opportunities: {len(music_swells)}")
   print(f"\n→ Saved to {output_path}")




if __name__ == "__main__":
   run()



