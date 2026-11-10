#!/usr/bin/env python3
"""
Step 6: Parse asset_acquisition.md → JSON, then write AI generation prompts.


Reads:  workspace/asset_acquisition.md
Writes: workspace/asset_acquisition.json
       assets/scene_X/asset_X/generated.txt (AI prompts for manual generation)
"""


import json
from pathlib import Path
from collections import defaultdict
import re


BASE_DIR = Path(__file__).parent.parent
WORKSPACE = BASE_DIR / "workspace"
ASSETS_DIR = BASE_DIR / "assets"
STATE_FILE = WORKSPACE / "fetch_state.json"




# ----------------------------
# PARSING
# ----------------------------


def clean_value(v):
   v = v.strip()
   return None if v in ["N/A", ""] else v




def parse_asset_acquisition(text):
   scenes = defaultdict(list)
   current_scene = None
   current_asset = None
   current_section = None


   for raw in text.splitlines():
       line = raw.rstrip()
       if not line.strip():
           continue


       m = re.match(r"^SCENE\s+(\d+)$", line.strip())
       if m:
           if current_asset:
               scenes[current_scene].append(current_asset)
           current_scene = f"scene_{m.group(1)}"
           current_asset = None
           current_section = None
           continue


       m = re.match(r"^ASSET\s+(\d+)$", line.strip())
       if m:
           if current_asset:
               scenes[current_scene].append(current_asset)
           current_asset = {
               "asset_id": int(m.group(1)),
               "type": None,
               "visual_goal": None,
               "priority": None,
               "duration": None,
               "ai_prompt": None,
           }
           current_section = None
           continue


       if current_asset is None:
           continue


       stripped = line.strip()


       section_map = {
           "TYPE:": "type",
           "VISUAL_GOAL:": "visual_goal",
           "PRIORITY:": "priority",
           "DURATION:": "duration",
           "AI_PROMPT:": "ai_prompt",
       }


       matched_section = False
       for key, section_name in section_map.items():
           if stripped.startswith(key):
               current_section = section_name
               # Check for inline value (e.g., "TYPE: ai_image")
               inline_value = stripped[len(key):].strip()
               if inline_value and inline_value != "N/A":
                   current_asset[section_name] = clean_value(inline_value)
               matched_section = True
               break


       if matched_section:
           continue


       if current_section == "type":
           current_asset["type"] = clean_value(stripped)
       elif current_section == "visual_goal":
           current_asset["visual_goal"] = clean_value(stripped)
       elif current_section == "priority":
           current_asset["priority"] = clean_value(stripped)
       elif current_section == "duration":
           current_asset["duration"] = clean_value(stripped)
       elif current_section == "ai_prompt":
           if current_asset["ai_prompt"] is None:
               current_asset["ai_prompt"] = clean_value(stripped)
           elif current_asset["ai_prompt"]:
               current_asset["ai_prompt"] += " " + stripped


   if current_asset:
       scenes[current_scene].append(current_asset)


   return dict(scenes)




# ----------------------------
# ASSET PROCESSING
# ----------------------------


def has_media_files(folder):
   """Check if folder already has generated content."""
   media_exts = {".mp4", ".mov", ".avi", ".webm", ".png", ".jpg", ".jpeg", ".webp"}
   folder_path = Path(folder)
   if not folder_path.exists():
       return False
   for f in folder_path.iterdir():
       if f.suffix.lower() in media_exts:
           return True
   return False




def process_asset(asset, asset_folder):
   asset_type = asset["type"]
   Path(asset_folder).mkdir(parents=True, exist_ok=True)


   # Skip if folder already has media files (preserve existing generated content)
   if has_media_files(asset_folder):
       print(f"    → Skipping (already has media files)")
       return True


   # AI video/image — save prompt for manual Gemini/Imagen generation
   if asset_type in ("ai_video", "ai_image"):
       prompt = asset.get("ai_prompt") or asset.get("visual_goal") or ""
       with open(f"{asset_folder}/generated.txt", "w") as f:
           json.dump({"type": asset_type, "prompt": prompt}, f, indent=2)
       print(f"    → Saved AI prompt (generate manually)")
       return True


   print(f"    → Unknown asset type: {asset_type}")
   return False




# ----------------------------
# PIPELINE
# ----------------------------


def load_state():
   if STATE_FILE.exists():
       with open(STATE_FILE) as f:
           return json.load(f)
   return {}




def save_state(state):
   with open(STATE_FILE, "w") as f:
       json.dump(state, f, indent=2)




def run():
   # Step 1: Parse markdown → JSON
   md_path = WORKSPACE / "asset_acquisition.md"
   json_path = WORKSPACE / "asset_acquisition.json"


   if not md_path.exists():
       print(f"ERROR: {md_path} not found. Run Step 5 first.")
       return


   print("Parsing asset_acquisition.md → JSON...")
   text = md_path.read_text()
   data = parse_asset_acquisition(text)


   with open(json_path, "w") as f:
       json.dump(data, f, indent=2, ensure_ascii=False)
   print(f"  Parsed {len(data)} scenes, {sum(len(v) for v in data.values())} assets.")
   print()


   # Step 2: Process assets
   state = load_state()


   for scene_key, assets in data.items():
       if state.get(scene_key, {}).get("status") == "complete":
           print(f"Skipping {scene_key} (already complete)")
           continue


       print(f"Processing {scene_key}...")
       scene_success = True


       for asset in assets:
           asset_idx = asset["asset_id"]
           asset_folder = str(ASSETS_DIR / scene_key / f"asset_{asset_idx}")
           print(f"  Asset {asset_idx} ({asset['type']}):")


           success = process_asset(asset, asset_folder)
           if not success:
               scene_success = False


       state[scene_key] = {"status": "complete" if scene_success else "partial"}
       save_state(state)
       print(f"  → {scene_key}: {'complete' if scene_success else 'partial'}")
       print()


   print("Done! Check assets/ folder for results.")
   print("For scenes with generated.txt files, generate images/videos manually with Gemini/Imagen.")




if __name__ == "__main__":
   run()
