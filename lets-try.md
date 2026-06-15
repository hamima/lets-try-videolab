# How to Run the Pipeline


## Prerequisites


```bash
pip install moviepy requests google
brew install ffmpeg


# Set API keys
export PEXELS_API_KEY="your_pexels_api_key_here"
export PIXABAY_API_KEY="your_pixabay_api_key_here"
export GROUNDING_API_KEY="your_grounding_api_key_here"





```


---


## Step-by-Step Execution


### STEP 1: Research
```bash
python pipeline.py prompt 1
```
- Copy the prompt
- Paste into Claude/Gemini/ChatGPT along with your topic idea
- Save output → `workspace/research_dossier.md`




---


### STEP 2: Story Script
```bash
python pipeline.py prompt 2
```
- Copy the prompt
- Paste into LLM with content of `workspace/research_dossier.md` as input
- Save output → `workspace/story_script.md`


---


### STEP 3: Scene Breakdown
```bash
python pipeline.py prompt 3
```
- Copy the prompt
- Paste into LLM with content of `workspace/story_script.md` as input
- Save output → `workspace/scene_plan.md`


---


### STEP 4: Asset Planning
```bash
python pipeline.py prompt 4
```
- Copy the prompt
- Paste into LLM with content of `workspace/scene_plan.md` as input
- Save output → `workspace/asset_manifest.md`


---


### STEP 5: Asset Acquisition Instructions
```bash
python pipeline.py prompt 5
```
- Copy the prompt
- Paste into LLM with content of `workspace/asset_manifest.md` as input
- Save output → `workspace/asset_acquisition.md`


---


### STEP 6: Fetch Assets (AUTOMATED)
```bash
python pipeline.py run 6
```
- Parses `asset_acquisition.md` → JSON
- Downloads stock videos and photos from Pexels/Pixabay
- Saves AI prompts as `generated.txt` for manual generation
- Output → `assets/scene_X/asset_X/`


---


### STEP 7: Generate AI Images (MANUAL - Gemini)
- Look in `assets/` for folders containing `generated.txt`
- Open each `generated.txt` — it contains an image generation prompt
- Paste prompt into Gemini (Imagen/Veo)
- Download generated image → save as `.png` in the same folder


```bash
# Find which scenes need AI generation:
find assets/ -name "generated.txt" -exec echo {} \;
```


---


### STEP 8: Narration Script
```bash
python pipeline.py prompt 8
```
- Copy the prompt
- Paste into LLM with content of `workspace/story_script.md` as input
- Save output → `workspace/narration_script.txt`


> NOTE: Steps 8-11 can run IN PARALLEL with Steps 6-7


---


### STEP 9: Generate Narration Audio (MANUAL - ElevenLabs)
- Open `workspace/narration_script.txt`
- Copy ONLY the "ELEVENLABS VERSION" section (the clean text with no scene headers)
- Paste into ElevenLabs Text-to-Speech
- Choose a deep, authoritative male voice (e.g., "Adam" or "Daniel")
- Generate and download → save as `workspace/narration.mp3`


---


### STEP 10: Music Prompt
```bash
python pipeline.py prompt 10
```
- Copy the prompt
- Paste into LLM with content of `workspace/scene_plan.md` as input
- LLM outputs a single paragraph — that IS your ElevenLabs music prompt
- Save output → `workspace/music_prompt.txt`


---


### STEP 11: Generate Music Audio (MANUAL - ElevenLabs)
- Open `workspace/music_prompt.txt`
- Copy the entire paragraph
- Paste into ElevenLabs Music Generation
- Generate and download → save as `workspace/music.wav`


---


### STEP 12: Asset Inventory (AUTOMATED)
```bash
python pipeline.py run 12
```
- Scans all `assets/` folders
- Produces a detailed inventory of every file, resolution, duration
- Output → `workspace/asset_inventory.txt`


---


### STEP 12b: Narration Timing Analysis (AUTOMATED)
```bash
python pipeline.py run 12b
```
- Analyzes `narration.mp3` using FFmpeg silence detection
- Extracts per-scene start/end timestamps from actual audio
- Identifies music swell points (long pauses between scenes)
- Output → `workspace/narration_timing.json`


> NOTE: This MUST run after narration.mp3 exists (Step 9). Output is used by both Step 13 (EDL) and Step 14 (assembly).


---


### STEP 13: Edit Decision List (MANUAL - Gemini)
```bash
python pipeline.py prompt 13
```
- Copy the prompt from `prompts/08_creative_director.md`
- Paste into Gemini Pro along with the FULL content of `workspace/asset_inventory.txt`
- Gemini outputs a JSON edit decision list
- Save the JSON output → `workspace/edl.json`


---


### STEP 14: Final Assembly (AUTOMATED)
```bash
python pipeline.py run 14
```
- Reads `edl.json`
- Selects and trims clips per Gemini's decisions
- Applies Ken Burns to images
- Layers narration at full volume + music at 15%
- Exports → `output/final_video.mp4`


---


## Quick Reference


```bash
# Check what's done
python pipeline.py status


# View any prompt
python pipeline.py prompt <step_number>


# Run automated steps
python pipeline.py run 6      # fetch assets
python pipeline.py run 12     # generate inventory
python pipeline.py run 14     # assemble video
python pipeline.py run all    # run all automated steps


# Reset pipeline
python pipeline.py clean
```


---


## Parallel Execution Map


```
Steps 1→2→3→4→5→6→7 (content + assets track)
                 ↘
Steps 1→2→(8→9)    → 12→13→14
      ↘ (10→11) ↗
        (audio track)
```


After Step 2 (story script), you can split into parallel tracks:
- **Track A**: Steps 3→4→5→6→7 (scene breakdown + assets)
- **Track B**: Steps 8→9 (narration)
- **Track C**: Steps 10→11 (music) — needs Step 3 output


All tracks converge at Step 12 (inventory) which needs assets + audio complete.


---


## Troubleshooting


| Problem | Fix |
|---------|-----|
| Corrupted .mp4 files | Delete and re-fetch, or script uses black placeholder |
| Scene has no assets | Check `generated.txt` exists → generate with Gemini |
| Photos saved as .jpg but corrupt | Was using video API — fixed in `fetch_assets.py` |
| MoviePy `looped` error | Already fixed — uses concatenation instead |
| ffprobe parse error | Corrupted file — script skips gracefully |
| Music too loud/quiet | Edit `music_volume` in `edl.json` (0.0–1.0) |