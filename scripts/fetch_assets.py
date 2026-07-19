#!/usr/bin/env python3
"""
Step 6: Parse asset_acquisition.md → JSON, then fetch stock/photo assets.


Reads:  workspace/asset_acquisition.md
Writes: workspace/asset_acquisition.json
       assets/scene_X/asset_X/*.mp4 (videos)
       assets/scene_X/asset_X/*.jpg (photos)
       assets/scene_X/asset_X/generated.txt (AI prompts for manual generation)
"""


import os
import re
import time
import json
import requests
from pathlib import Path
from collections import defaultdict


BASE_DIR = Path(__file__).parent.parent
WORKSPACE = BASE_DIR / "workspace"
ASSETS_DIR = BASE_DIR / "assets"
STATE_FILE = WORKSPACE / "fetch_state.json"


PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")




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
               "search_variations": [],
               "ai_prompt": None,
               "chart_spec": None,
               "map_spec": None,
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
           "SEARCH_VARIATIONS:": "search_variations",
           "AI_PROMPT:": "ai_prompt",
           "CHART_SPEC:": "chart_spec",
           "MAP_SPEC:": "map_spec",
       }


       matched_section = False
       for key, section_name in section_map.items():
           if stripped.startswith(key):
               current_section = section_name
               # Check for inline value (e.g., "TYPE: photo")
               inline_value = stripped[len(key):].strip()
               if inline_value and inline_value != "N/A":
                   if section_name == "search_variations":
                       current_asset["search_variations"].append(inline_value)
                   else:
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
       elif current_section == "search_variations":
           if stripped not in ["1.", "2.", "3.", "4."]:
               current_asset["search_variations"].append(stripped)
       elif current_section == "ai_prompt":
           if current_asset["ai_prompt"] is None:
               current_asset["ai_prompt"] = clean_value(stripped)
           elif current_asset["ai_prompt"]:
               current_asset["ai_prompt"] += " " + stripped
       elif current_section == "chart_spec":
           if current_asset["chart_spec"] is None:
               current_asset["chart_spec"] = clean_value(stripped)
           elif current_asset["chart_spec"]:
               current_asset["chart_spec"] += " " + stripped
       elif current_section == "map_spec":
           if current_asset["map_spec"] is None:
               current_asset["map_spec"] = clean_value(stripped)
           elif current_asset["map_spec"]:
               current_asset["map_spec"] += " " + stripped


   if current_asset:
       scenes[current_scene].append(current_asset)


   return dict(scenes)




# ----------------------------
# FETCH FUNCTIONS
# ----------------------------


def fetch_pexels_videos(query):
   if not PEXELS_API_KEY:
       return []
   url = "https://api.pexels.com/videos/search"
   headers = {"Authorization": PEXELS_API_KEY}
   params = {"query": query, "per_page": 5}
   try:
       r = requests.get(url, headers=headers, params=params, timeout=10)
       if r.status_code != 200:
           print(f"    [Pexels Videos] {r.status_code}")
           return []
       return [v["video_files"][0]["link"] for v in r.json().get("videos", [])[:4] if v.get("video_files")]
   except Exception as e:
       print(f"    [Pexels Videos] error: {e}")
       return []




def fetch_pixabay_videos(query):
   if not PIXABAY_API_KEY:
       return []
   url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}"
   try:
       r = requests.get(url, timeout=10)
       if r.status_code != 200:
           print(f"    [Pixabay Videos] {r.status_code}")
           return []
       return [item["videos"]["medium"]["url"] for item in r.json().get("hits", [])[:4] if "videos" in item]
   except Exception as e:
       print(f"    [Pixabay Videos] error: {e}")
       return []




def fetch_pexels_photos(query):
   if not PEXELS_API_KEY:
       return []
   url = "https://api.pexels.com/v1/search"
   headers = {"Authorization": PEXELS_API_KEY}
   params = {"query": query, "per_page": 5}
   try:
       r = requests.get(url, headers=headers, params=params, timeout=10)
       if r.status_code != 200:
           print(f"    [Pexels Photos] {r.status_code}")
           return []
       return [p["src"]["large2x"] for p in r.json().get("photos", [])[:4]]
   except Exception as e:
       print(f"    [Pexels Photos] error: {e}")
       return []




def fetch_pixabay_photos(query):
   if not PIXABAY_API_KEY:
       return []
   url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo"
   try:
       r = requests.get(url, timeout=10)
       if r.status_code != 200:
           print(f"    [Pixabay Photos] {r.status_code}")
           return []
       return [item["largeImageURL"] for item in r.json().get("hits", [])[:4] if "largeImageURL" in item]
   except Exception as e:
       print(f"    [Pixabay Photos] error: {e}")
       return []




def fetch_google_videos(query):
   if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
       return []
   url = "https://www.googleapis.com/customsearch/v1"
   params = {
       "key": GOOGLE_CSE_API_KEY,
       "cx": GOOGLE_CSE_CX,
       "q": query + " stock footage",
       "searchType": "image",
       "fileType": "mp4",
       "num": 5,
   }
   try:
       r = requests.get(url, params=params, timeout=10)
       if r.status_code != 200:
           print(f"    [Google CSE Videos] {r.status_code}: {r.text[:100]}")
           return []
       items = r.json().get("items", [])
       return [item["link"] for item in items if item.get("link")]
   except Exception as e:
       print(f"    [Google CSE Videos] error: {e}")
       return []




def fetch_google_images(query):
   if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
       return []
   url = "https://www.googleapis.com/customsearch/v1"
   params = {
       "key": GOOGLE_CSE_API_KEY,
       "cx": GOOGLE_CSE_CX,
       "q": query,
       "searchType": "image",
       "imgSize": "xlarge",
       "num": 5,
   }
   try:
       r = requests.get(url, params=params, timeout=10)
       if r.status_code != 200:
           print(f"    [Google CSE Images] {r.status_code}: {r.text[:100]}")
           return []
       items = r.json().get("items", [])
       return [item["link"] for item in items if item.get("link")]
   except Exception as e:
       print(f"    [Google CSE Images] error: {e}")
       return []




def download_file(url, path, timeout=30):
   try:
       r = requests.get(url, stream=True, timeout=timeout)
       if r.status_code == 200:
           with open(path, "wb") as f:
               for chunk in r.iter_content(8192):
                   f.write(chunk)
           return True
   except Exception as e:
       print(f"    [Download] failed: {e}")
   return False




# ----------------------------
# ASSET PROCESSING
# ----------------------------


def has_media_files(folder):
   """Check if folder already has video or image files."""
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


   # AI video/image — save prompt for manual Gemini generation
   if asset_type == "ai_video":
       prompt = asset.get("ai_prompt") or asset.get("visual_goal") or ""
       with open(f"{asset_folder}/generated.txt", "w") as f:
           json.dump({"type": "ai_video", "prompt": prompt}, f, indent=2)
       print(f"    → Saved AI prompt (generate manually with Gemini)")
       return True


   # Chart/Map — save spec for manual creation
   if asset_type in ["chart", "map"]:
       spec = asset.get("chart_spec") or asset.get("map_spec") or ""
       with open(f"{asset_folder}/generated.json", "w") as f:
           json.dump({"type": asset_type, "spec": spec}, f, indent=2)
       print(f"    → Saved {asset_type} spec (create manually)")
       return True


   # Stock video or editorial video — Google CSE primary, Pexels/Pixabay fallback
   if asset_type in ["stock_video", "editorial_video"]:
       success = False
       for q_idx, query in enumerate(asset.get("search_variations", []), start=1):
           # Primary: Google Custom Search
           urls = fetch_google_videos(query)
           # Fallback: Pexels + Pixabay
           if not urls:
               urls = fetch_pexels_videos(query) + fetch_pixabay_videos(query)
           for v_idx, url in enumerate(urls[:4], start=1):
               file_path = f"{asset_folder}/q{q_idx}_v{v_idx}.mp4"
               if download_file(url, file_path):
                   success = True
           time.sleep(0.5)
       # If no videos found, try Google image search as last resort
       if not success:
           for q_idx, query in enumerate(asset.get("search_variations", []), start=1):
               urls = fetch_google_images(query)
               for v_idx, url in enumerate(urls[:4], start=1):
                   ext = ".jpg"
                   if ".png" in url.lower():
                       ext = ".png"
                   file_path = f"{asset_folder}/q{q_idx}_img{v_idx}{ext}"
                   if download_file(url, file_path):
                       success = True
               time.sleep(0.5)
       return success


   # Photo — Google CSE primary, Pexels/Pixabay fallback
   if asset_type == "photo":
       success = False
       for q_idx, query in enumerate(asset.get("search_variations", []), start=1):
           # Primary: Google Custom Search
           urls = fetch_google_images(query)
           # Fallback: Pexels + Pixabay
           if not urls:
               urls = fetch_pexels_photos(query) + fetch_pixabay_photos(query)
           for v_idx, url in enumerate(urls[:4], start=1):
               file_path = f"{asset_folder}/q{q_idx}_v{v_idx}.jpg"
               if download_file(url, file_path):
                   success = True
           time.sleep(0.5)
       return success


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
   # Check for API keys
   if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
       print("WARNING: GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX not set (primary source).")
       print("  export GOOGLE_CSE_API_KEY='your_key'")
       print("  export GOOGLE_CSE_CX='your_search_engine_id'")
       print()
   if not PEXELS_API_KEY or not PIXABAY_API_KEY:
       print("NOTE: PEXELS_API_KEY / PIXABAY_API_KEY not set (fallback sources).")
       print()


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


   # Step 2: Fetch assets
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
   print("For scenes with generated.txt files, generate images manually with Gemini.")




if __name__ == "__main__":
   run()



