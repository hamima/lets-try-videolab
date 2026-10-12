#!/usr/bin/env python3
"""
Step 12: Generate asset inventory for the creative director.


Reads:  assets/ (all scene folders)
       workspace/scene_plan.md
Writes: workspace/asset_inventory.txt
"""


import json
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
# WORKSPACE_DIR is set by backend/tasks.py's _run_script() to the per-run workspace
# (workspace/<domain>/<run_id>); fall back to the repo-root workspace/ for standalone use.
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))
ASSETS_DIR = WORKSPACE / "assets"




def get_media_info(filepath: Path) -> dict:
   try:
       result = subprocess.run(
           ["ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_entries", "format=duration,size",
            "-show_entries", "stream=width,height",
            str(filepath)],
           capture_output=True, text=True, timeout=10
       )
       data = json.loads(result.stdout)
       info = {}
       if data.get("format"):
           info["duration_sec"] = round(float(data["format"].get("duration", 0)), 1)
           info["size_mb"] = round(int(data["format"].get("size", 0)) / 1024 / 1024, 2)
       if data.get("streams"):
           for stream in data["streams"]:
               if "width" in stream:
                   info["resolution"] = f"{stream['width']}x{stream['height']}"
                   info["aspect"] = "landscape" if stream["width"] > stream["height"] else "portrait"
                   break
       return info
   except Exception:
       return {}




def run():
   output_lines = []


   def out(text=""):
       output_lines.append(text)
       print(text)


   out("=" * 60)
   out("ASSET INVENTORY FOR CREATIVE DIRECTOR")
   out("=" * 60)
   out()


   # Include scene plan
   scene_plan = WORKSPACE / "scene_plan.md"
   if scene_plan.exists():
       out("SCENE PLAN:")
       out(scene_plan.read_text())
       out()


   out("=" * 60)
   out("AVAILABLE ASSETS PER SCENE")
   out("=" * 60)
   out()


   # Find scene count
   scene_dirs = sorted(ASSETS_DIR.glob("scene_*"), key=lambda p: int(p.name.split("_")[1]))


   if not scene_dirs:
       out("  NO ASSETS FOUND. Run Step 6 first.")
       sys.exit(1)


   for scene_dir in scene_dirs:
       scene_num = scene_dir.name.split("_")[1]
       out(f"--- SCENE {scene_num} ---")


       videos = sorted(scene_dir.rglob("*.mp4"))
       images = sorted(
           list(scene_dir.rglob("*.jpg")) +
           list(scene_dir.rglob("*.png")) +
           list(scene_dir.rglob("*.webp"))
       )


       if not videos and not images:
           txt_files = list(scene_dir.rglob("*.txt"))
           json_files = list(scene_dir.rglob("*.json"))
           if txt_files or json_files:
               out("  STATUS: Prompt exists, asset not yet generated")
               for tf in txt_files:
                   try:
                       data = json.loads(tf.read_text())
                       out(f"  PROMPT: {data.get('prompt', 'N/A')[:100]}...")
                   except Exception:
                       pass
           else:
               out("  NO ASSETS")
           out()
           continue


       # Group by asset folder
       asset_folders = set()
       for f in videos + images:
           rel = f.relative_to(scene_dir)
           asset_folders.add(rel.parts[0] if len(rel.parts) > 1 else "root")


       for folder_name in sorted(asset_folders):
           if folder_name == "root":
               folder_path = scene_dir
           else:
               folder_path = scene_dir / folder_name


           folder_videos = sorted(folder_path.glob("*.mp4"))
           folder_images = sorted(
               list(folder_path.glob("*.jpg")) +
               list(folder_path.glob("*.png")) +
               list(folder_path.glob("*.webp"))
           )


           out(f"  {folder_name}/")


           # Categorize
           quality_groups = {}
           standalone = []
           for f in folder_videos + folder_images:
               parts = f.stem.split("_")
               if len(parts) >= 2 and parts[0].startswith("q"):
                   prefix = parts[0]
                   if prefix not in quality_groups:
                       quality_groups[prefix] = []
                   quality_groups[prefix].append(f)
               else:
                   standalone.append(f)


           for qprefix in sorted(quality_groups.keys()):
               files = quality_groups[qprefix]
               out(f"    {qprefix} group: {len(files)} variants")
               for f in files:
                   info = get_media_info(f)
                   out(f"      {f.name} | "
                       f"res={info.get('resolution', '?')} | "
                       f"aspect={info.get('aspect', '?')} | "
                       f"dur={info.get('duration_sec', '?')}s | "
                       f"type={f.suffix}")
               landscape_in_group = [f for f in files
                                     if get_media_info(f).get('aspect') == 'landscape']
               if landscape_in_group:
                   best = max(landscape_in_group,
                              key=lambda f: int(get_media_info(f).get('resolution', '0x0').split('x')[0]))
                   out(f"      BEST (highest res landscape): {best.name}")


           for f in standalone:
               info = get_media_info(f)
               out(f"    {f.name} | "
                   f"res={info.get('resolution', '?')} | "
                   f"aspect={info.get('aspect', '?')} | "
                   f"type={f.suffix}")


           landscape = [f for f in folder_videos + folder_images if "q1" in f.stem or "q2" in f.stem]
           if landscape:
               out(f"    LANDSCAPE OPTIONS: {[f.name for f in landscape[:4]]}")


       out()


   # Audio info
   out("=" * 60)
   out("AUDIO FILES")
   out("=" * 60)
   narration = WORKSPACE / "narration.mp3"
   music = WORKSPACE / "music.wav"
   if narration.exists():
       info = get_media_info(narration)
       out(f"  Narration: {info.get('duration_sec', '?')}s ({narration})")
   else:
       out("  Narration: NOT FOUND (place narration.mp3 in workspace/)")
   if music.exists():
       info = get_media_info(music)
       out(f"  Music: {info.get('duration_sec', '?')}s ({music})")
   else:
       out("  Music: NOT FOUND (place music.wav in workspace/)")


   # Write to file
   inventory_path = WORKSPACE / "asset_inventory.txt"
   inventory_path.write_text("\n".join(output_lines))
   print(f"\n→ Saved to {inventory_path}")




if __name__ == "__main__":
   run()



