#!/usr/bin/env python3
"""
Documentary Video Production Pipeline
======================================


Orchestrates the full pipeline from topic research to final video.


PIPELINE STEPS:
   Step 1: Research         → research_dossier.md        [LLM - manual]
   Step 2: Story Script     → story_script.md            [LLM - manual]
   Step 3: Scene Breakdown  → scene_plan.md              [LLM - manual]
   Step 4: Asset Planning   → asset_manifest.md          [LLM - manual]
   Step 5: Asset Acquisition→ asset_acquisition.md/json  [LLM + script]
   Step 6: Asset Fetching   → assets/scene_X/            [automated]
   Step 7: AI Image Gen     → assets/scene_X/            [Gemini - manual]
   Step 8: Narration Script → narration_script.txt       [LLM - manual]
   Step 8b: Split Narration → narration_scenes/*.txt     [automated]
   Step 9: Narration Audio  → narration_scenes/*.mp3     [ElevenLabs - manual, per scene]
   Step 10: Music Prompt    → music_prompt.txt           [LLM - manual]
   Step 11: Music Audio     → music.wav                  [ElevenLabs - manual]
   Step 12: Asset Inventory → asset_inventory.txt        [automated]
   Step 12b: Timing Build   → narration_timing.json      [automated]
   Step 13: Edit Decision   → edl.json                   [Gemini - manual]
   Step 14: Final Assembly  → output/final_video.mp4     [automated]


Usage:
   python pipeline.py status          # Show pipeline progress
   python pipeline.py run <step>      # Run a specific automated step
   python pipeline.py run all         # Run all automated steps in sequence
   python pipeline.py config "<topic>" [language]  # Set topic & language
   python pipeline.py prompt <step>   # Print the prompt for a manual step
   python pipeline.py clean           # Reset pipeline state
"""


import sys
import os
import json
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).parent
WORKSPACE = BASE_DIR / "workspace"
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
PROMPTS_DIR = BASE_DIR / "prompts"
SCRIPTS_DIR = BASE_DIR / "scripts"
STATE_FILE = WORKSPACE / "pipeline_state.json"
CONFIG_FILE = WORKSPACE / "project_config.json"




def load_project_config():
   if CONFIG_FILE.exists():
       return json.loads(CONFIG_FILE.read_text())
   return {}




def save_project_config(config):
   WORKSPACE.mkdir(parents=True, exist_ok=True)
   CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))


STEPS = [
   {
       "id": 1,
       "name": "Research",
       "type": "manual_llm",
       "prompt": "01_research.md",
       "input": None,
       "output": "research_dossier.md",
       "description": "Research a topic using the investigative journalist prompt"
   },
   {
       "id": 2,
       "name": "Story Script",
       "type": "manual_llm",
       "prompt": "02_story.md",
       "input": "research_dossier.md",
       "output": "story_script.md",
       "description": "Convert research into a 3-minute documentary script"
   },
   {
       "id": 3,
       "name": "Scene Breakdown",
       "type": "manual_llm",
       "prompt": "03_scene_breakdown.md",
       "input": "story_script.md",
       "output": "scene_plan.md",
       "description": "Break script into individual scenes with timing"
   },
   {
       "id": 4,
       "name": "Asset Planning",
       "type": "manual_llm",
       "prompt": "04_asset_planning.md",
       "input": "scene_plan.md",
       "output": "asset_manifest.md",
       "description": "Determine what visual assets each scene needs"
   },
   {
       "id": 5,
       "name": "Asset Acquisition Instructions",
       "type": "manual_llm",
       "prompt": "05_asset_acquisition.md",
       "input": "asset_manifest.md",
       "output": "asset_acquisition.md",
       "description": "Convert asset plan into machine-executable retrieval instructions"
   },
   {
       "id": 6,
       "name": "Parse & Fetch Assets",
       "type": "automated",
       "script": "fetch_assets.py",
       "input": "asset_acquisition.md",
       "output": "assets/",
       "description": "Parse acquisition doc to JSON, then fetch stock videos/photos"
   },
   {
       "id": 7,
       "name": "Generate AI Images",
       "type": "manual_gemini",
       "input": "assets/scene_X/asset_X/generated.txt",
       "output": "assets/scene_X/asset_X/*.png",
       "description": "Use Gemini Veo/Imagen to generate images from prompts in generated.txt files"
   },
   {
       "id": 8,
       "name": "Narration Script",
       "type": "manual_llm",
       "prompt": "06_narration.md",
       "input": "story_script.md",
       "output": "narration_script.txt",
       "description": "Convert story script into ElevenLabs-optimized narration text"
   },
   {
       "id": "8b",
       "name": "Split Narration Per Scene",
       "type": "automated",
       "script": "split_narration.py",
       "input": "scene_plan.md",
       "output": "narration_scenes/scene_*.txt",
       "description": "Split narration text into per-scene files for individual TTS generation"
   },
   {
       "id": 9,
       "name": "Generate Narration Audio (Per Scene)",
       "type": "manual_elevenlabs",
       "input": "narration_scenes/scene_*.txt",
       "output": "narration_scenes/scene_*.mp3",
       "description": "For each scene_XX.txt in workspace/narration_scenes/, paste into ElevenLabs TTS → save as scene_XX.mp3 in same folder"
   },
   {
       "id": 10,
       "name": "Music Prompt",
       "type": "manual_llm",
       "prompt": "07_music.md",
       "input": "scene_plan.md",
       "output": "music_prompt.txt",
       "description": "Generate ElevenLabs music prompt from scene plan"
   },
   {
       "id": 11,
       "name": "Generate Music Audio",
       "type": "manual_elevenlabs",
       "input": "music_prompt.txt",
       "output": "music.wav",
       "description": "Paste music_prompt.txt into ElevenLabs Music Gen → download as music.wav"
   },
   {
       "id": 12,
       "name": "Asset Inventory",
       "type": "automated",
       "script": "generate_inventory.py",
       "input": "assets/",
       "output": "asset_inventory.txt",
       "description": "Scan all assets and produce inventory for creative director"
   },
   {
       "id": "12b",
       "name": "Build Narration Timing",
       "type": "automated",
       "script": "build_narration_timing.py",
       "input": "narration_scenes/scene_*.mp3",
       "output": "narration_timing.json",
       "description": "Build per-scene timing from individual audio files, concatenate into narration.mp3"
   },
   {
       "id": 13,
       "name": "Edit Decision List",
       "type": "manual_gemini",
       "prompt": "08_creative_director.md",
       "input": "asset_inventory.txt",
       "output": "edl.json",
       "description": "Feed inventory + timing + creative_director prompt to Gemini → save as edl.json"
   },
   {
       "id": 14,
       "name": "Final Assembly",
       "type": "automated",
       "script": "assemble.py",
       "input": "edl.json",
       "output": "output/final_video.mp4",
       "description": "Assemble final video from EDL using MoviePy/FFmpeg"
   },
   {
       "id": 15,
       "name": "Viral Metadata",
       "type": "manual_llm",
       "prompt": "09_viral_metadata.md",
       "input": "research_dossier.md",
       "output": "viral_metadata.txt",
       "description": "Generate viral hashtags, title, description, and tags for YouTube/social media"
   },
]




def load_state():
   if STATE_FILE.exists():
       with open(STATE_FILE) as f:
           return json.load(f)
   return {"completed": [], "current_step": 1}




def save_state(state):
   WORKSPACE.mkdir(parents=True, exist_ok=True)
   with open(STATE_FILE, "w") as f:
       json.dump(state, f, indent=2)




def check_output_exists(step):
   output = step["output"]
   if output.endswith("/"):
       return (BASE_DIR / output).exists() and any((BASE_DIR / output).iterdir())
   return (WORKSPACE / output).exists() or (BASE_DIR / output).exists()




def find_step(step_id):
   """Find a step by its ID (supports int or string like '12b')."""
   for step in STEPS:
       if str(step["id"]) == str(step_id):
           return step
   return None




def show_status():
   state = load_state()
   print("\n" + "=" * 65)
   print("  DOCUMENTARY PIPELINE STATUS")
   print("=" * 65 + "\n")


   for step in STEPS:
       exists = check_output_exists(step)
       status = "DONE" if exists else "PENDING"
       icon = "[+]" if exists else "[ ]"
       step_type = step["type"].replace("manual_", "").replace("automated", "AUTO")
       sid = str(step['id'])
       print(f"  {icon} Step {sid:<3s} | {step['name']:<30s} | {step_type:<10s} | {status}")


   print("\n" + "-" * 65)
   print("  Legend: [+] = output exists, [ ] = not yet done")
   print("  Types: llm = paste prompt into LLM, gemini = use Gemini,")
   print("         elevenlabs = use ElevenLabs, AUTO = run script")
   print("-" * 65 + "\n")




def extract_narration_from_story(story_path):
   """Extract only the spoken narration paragraphs from story_script.md."""
   text = story_path.read_text()
   lines = text.split("\n")
   narration_lines = []
   in_narration = False
   for line in lines:
       if "FULL NARRATION SCRIPT" in line:
           in_narration = True
           continue
       if in_narration:
           if line.strip().startswith("KEY TAKEAWAYS"):
               break
           # Skip timestamp headers and dividers
           if line.strip().startswith("###") or line.strip() == "---":
               continue
           if line.strip():
               narration_lines.append(line.strip())
   return "\n\n".join(narration_lines)




def show_prompt(step_id):
   step = find_step(step_id)
   if not step:
       print(f"Step {step_id} not found")
       return
   if "prompt" not in step:
       print(f"Step {step_id} ({step['name']}) has no prompt — it's {step['type']}")
       return


   prompt_file = PROMPTS_DIR / step["prompt"]
   if not prompt_file.exists():
       print(f"Prompt file not found: {prompt_file}")
       return


   prompt_text = prompt_file.read_text()


   # For step 1 (research), inject topic and language
   if str(step_id) == "1":
       config = load_project_config()
       topic = config.get("topic", "<<TOPIC NOT SET — run: python pipeline.py config>>")
       language = config.get("language", "English")
       prompt_text = prompt_text.replace("{{topic}}", topic)
       prompt_text = prompt_text.replace("{{language}}", language)


   # For step 15 (viral metadata), inject topic, language, and research dossier
   if str(step_id) == "15":
       config = load_project_config()
       topic = config.get("topic", "<<TOPIC NOT SET>>")
       language = config.get("language", "English")
       prompt_text = prompt_text.replace("{{topic}}", topic)
       prompt_text = prompt_text.replace("{{language}}", language)
       dossier_path = WORKSPACE / "research_dossier.md"
       if dossier_path.exists():
           prompt_text = prompt_text.replace("{{research_dossier}}", dossier_path.read_text())
       else:
           prompt_text = prompt_text.replace("{{research_dossier}}", "<<research_dossier.md not found — run Step 1 first>>")


   # For step 8 (narration), auto-insert extracted narration text
   if str(step_id) == "8" and "{{narration_only}}" in prompt_text:
       story_path = WORKSPACE / "story_script.md"
       if story_path.exists():
           narration = extract_narration_from_story(story_path)
           prompt_text = prompt_text.replace("{{narration_only}}", narration)


   print(f"\n{'=' * 65}")
   print(f"  PROMPT FOR STEP {step_id}: {step['name']}")
   print(f"  Input needed: {step.get('input', 'none')}")
   print(f"  Save output as: workspace/{step['output']}")
   print(f"{'=' * 65}\n")
   print(prompt_text)




def run_step(step_id):
   step = find_step(step_id)
   if not step:
       print(f"Step {step_id} not found")
       return


   if step["type"] != "automated":
       print(f"\nStep {step_id} ({step['name']}) is manual ({step['type']})")
       print(f"  → Use: python pipeline.py prompt {step_id}")
       print(f"  → Save output to: workspace/{step['output']}")
       return


   script_path = SCRIPTS_DIR / step["script"]
   if not script_path.exists():
       print(f"Script not found: {script_path}")
       return


   print(f"\nRunning Step {step_id}: {step['name']}...")
   print(f"  Script: {script_path}")
   print(f"  Output: {step['output']}")
   print()


   result = subprocess.run(
       [sys.executable, str(script_path)],
       cwd=str(BASE_DIR)
   )


   if result.returncode == 0:
       print(f"\n  Step {step_id} completed successfully!")
       state = load_state()
       if step_id not in state["completed"]:
           state["completed"].append(step_id)
       save_state(state)
   else:
       print(f"\n  Step {step_id} failed with exit code {result.returncode}")




def run_all_auto():
   for step in STEPS:
       if step["type"] == "automated":
           run_step(step["id"])




def clean():
   if STATE_FILE.exists():
       STATE_FILE.unlink()
       print("Pipeline state reset.")




def main():
   if len(sys.argv) < 2:
       print(__doc__)
       return


   cmd = sys.argv[1]


   if cmd == "status":
       show_status()
   elif cmd == "config":
       config = load_project_config()
       if len(sys.argv) < 3:
           print("\nProject Config:")
           print(f"  Topic:    {config.get('topic', '(not set)')}")
           print(f"  Language: {config.get('language', '(not set)')}")
           print(f"\nUsage: python pipeline.py config \"<topic>\" [language]")
           print(f"Example: python pipeline.py config \"Foreign policy of Jaishankar\" Hindi")
           return
       config["topic"] = sys.argv[2]
       config["language"] = sys.argv[3] if len(sys.argv) > 3 else "English"
       save_project_config(config)
       print(f"\n  Topic:    {config['topic']}")
       print(f"  Language: {config['language']}")
       print(f"  Saved to: {CONFIG_FILE}")
   elif cmd == "prompt":
       if len(sys.argv) < 3:
           print("Usage: python pipeline.py prompt <step_id>")
           return
       show_prompt(sys.argv[2])
   elif cmd == "run":
       if len(sys.argv) < 3:
           print("Usage: python pipeline.py run <step_id|all>")
           return
       if sys.argv[2] == "all":
           run_all_auto()
       else:
           run_step(sys.argv[2])
   elif cmd == "clean":
       clean()
   else:
       print(f"Unknown command: {cmd}")
       print("Commands: status, prompt, run, clean")




if __name__ == "__main__":
   main()



