#!/usr/bin/env python3
"""
Vid Life — Automated Pipeline
==============================

Replaces all manual pipeline steps with API calls:
  - Gemini 2.5 Pro  for LLM steps (1–5, 8, 10, 12, 16); falls back to Gemini 2.0 Flash on quota errors
  - Imagen 4        for AI image generation (step 7)
  - ComfyUI (RunPod pod) for video animation (step 9) — set COMFYUI_URL in .keys
  - ElevenLabs v3   for narration TTS (step 11) and music (step 13)
  - Built-in        for asset fetching (step 6), inventory, timing, and assembly (steps 14, 15, 17)

Domain selection:
  An interactive numbered menu lets the user pick the documentary domain at startup.
  Supported: political, general_knowledge, science, business, history, sports, technology
  Each domain has its own prompt files under prompts/{domain}/ and a dedicated voice ID.

Workspaces are scoped per domain: workspace/{domain}/YYYY-MM-DD_HHMMSS/
  The latest workspace for the chosen domain is auto-resumed on a full run.
  A fresh workspace is created if none exists for that domain.

Step 6 (Fetch Assets) runs entirely within this file — no external scripts needed.
  - ai_video assets: writes generated.txt with the Imagen prompt for step 7
  - map assets: writes map_spec.json
  - photo/video assets: downloads from Pexels

Usage:
    python automate.py              # pick domain, resume or start workspace
    python automate.py --step 3    # pick domain, re-run one step in latest workspace
    python automate.py --status    # pick domain, show status of latest workspace
"""

import sys
import os
import re
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# API KEYS
# ─────────────────────────────────────────────────────────────

GEMINI_API_KEY     = "${GEMINI_API_KEY}"
ELEVENLABS_API_KEY = "${ELEVENLABS_API_KEY}"
PEXELS_API_KEY     = "${PEXELS_API_KEY}"
PIXABAY_API_KEY    = "${PEXELS_API_KEY}"
COMFYUI_URL        = os.environ.get("COMFYUI_URL", "").rstrip("/")

# ─────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────

GEMINI_MODEL          = "gemini-2.5-pro"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"
IMAGEN_MODEL     = "imagen-4.0-generate-001"
ELEVENLABS_MODEL = "eleven_v3"

# ─────────────────────────────────────────────────────────────
# COMFYUI / WAN 2.1 ANIMATION CONFIG
# ─────────────────────────────────────────────────────────────

COMFYUI_FPS = 24

# Ken Burns key → motion prefix prepended to the Wan 2.1 prompt
BURN_KEY_PREFIXES = {
    "zoom_in":   "slow push in,",
    "zoom_out":  "slow pull back,",
    "pan_left":  "camera pan left,",
    "pan_right": "camera pan right,",
}


def _duration_to_frames(duration_str: str, fps: int = COMFYUI_FPS) -> int:
    """Parse '10 seconds', '5s', '20', etc. → frame count (minimum 16 frames)."""
    match = re.search(r"(\d+(?:\.\d+)?)", duration_str or "5")
    seconds = float(match.group(1)) if match else 5.0
    return max(16, int(seconds * fps))


# ─────────────────────────────────────────────────────────────
# DOMAIN → VOICE MAP
# Add or change voice IDs here to match your ElevenLabs library.
# ─────────────────────────────────────────────────────────────

DOMAIN_VOICE_MAP = {
    "political":         "pNInz6obpgDQGcFmaJgB",   # Adam
    "general_knowledge": "onwK4e9ZLuTAKqWW03F9",   # Daniel
    "science":           "N2lVS1w4EtoT3dr4eOWO",   # Callum
    "business":          "XB0fDUnXU5powFXDhCwa",   # Charlotte
    "history":           "IKne3meq5aSn9XLyUdCD",   # Charlie
    "sports":            "ErXwobaYiN019PkySvjV",   # Antoni (placeholder — swap in settings)
    "technology":        "pqHfZKP75CvOlQylNhV4",   # Bill
}
SUPPORTED_DOMAINS = list(DOMAIN_VOICE_MAP.keys())


# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).parent
PROMPTS_DIR    = BASE_DIR / "prompts"
SCRIPTS_DIR    = BASE_DIR / "scripts"
WORKSPACE_ROOT = BASE_DIR / "workspace"
OUTPUT_DIR     = BASE_DIR / "output"


# ─────────────────────────────────────────────────────────────
# STEP DEFINITIONS
# ─────────────────────────────────────────────────────────────

STEPS = [
    {
        "id": "1", "name": "Research", "type": "gemini",
        "inputs": {},
        "output": "research_dossier.md",
    },
    {
        "id": "2", "name": "Story Script", "type": "gemini",
        "inputs": {"research_dossier": "research_dossier.md"},
        "output": "story_script.md",
    },
    {
        "id": "3", "name": "Scene Breakdown", "type": "gemini",
        "inputs": {"story_script": "story_script.md"},
        "output": "scene_plan.md",
    },
    {
        "id": "4", "name": "Asset Manifest", "type": "gemini",
        "inputs": {"scene_plan": "scene_plan.md"},
        "output": "asset_manifest.md",
    },
    {
        "id": "5", "name": "Asset Acquisition Instructions", "type": "gemini",
        "inputs": {"asset_manifest": "asset_manifest.md"},
        "output": "asset_acquisition.md",
    },
    {
        "id": "6", "name": "Fetch Assets", "type": "fetch_assets",
        "output": "assets/",
    },
    {
        "id": "7", "name": "AI Image Generation", "type": "imagen",
        "output": "assets/",
    },
    {
        "id": "8", "name": "Animation Prompt", "type": "animation_prompt",
        "output": "assets/",
    },
    {
        "id": "9", "name": "ComfyUI Animation", "type": "runpod_animation",
        "output": "assets/",
    },
    {
        "id": "10", "name": "Narration Script", "type": "gemini",
        "inputs": {"story_script": "story_script.md"},
        "output": "narration_script.txt",
    },
    {
        "id": "11", "name": "Narration Audio", "type": "tts",
        "output": "narration.mp3",
    },
    {
        "id": "12", "name": "Music Prompt", "type": "gemini",
        "inputs": {"scene_plan": "scene_plan.md"},
        "output": "music_prompt.txt",
    },
    {
        "id": "13", "name": "Music Audio", "type": "music",
        "output": "music.wav",
    },
    {
        "id": "14", "name": "Asset Inventory", "type": "script",
        "script": "generate_inventory.py",
        "output": "asset_inventory.txt",
    },
    {
        "id": "15", "name": "Narration Timing", "type": "script",
        "script": "analyze_timing.py",
        "output": "narration_timing.json",
    },
    {
        "id": "16", "name": "Edit Decision List", "type": "gemini",
        "inputs": {
            "asset_inventory":  "asset_inventory.txt",
            "narration_timing": "narration_timing.json",
        },
        "output": "edl.json",
    },
    {
        "id": "17", "name": "Final Assembly", "type": "script",
        "script": "assemble.py",
        "output": "output/final_video.mp4",
    },
]



# ─────────────────────────────────────────────────────────────
# WORKSPACE & STATE
# ─────────────────────────────────────────────────────────────

def select_domain() -> str:
    """Show an interactive numbered menu and return the chosen domain."""
    print("\n  Select a domain:")
    for i, domain in enumerate(SUPPORTED_DOMAINS, 1):
        print(f"    {i}. {domain.replace('_', ' ').title()}")
    print()
    while True:
        choice = input("  Enter number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(SUPPORTED_DOMAINS):
            selected = SUPPORTED_DOMAINS[int(choice) - 1]
            print(f"  → {selected.replace('_', ' ').title()}\n")
            return selected
        print(f"  Invalid. Enter a number between 1 and {len(SUPPORTED_DOMAINS)}.")


def new_workspace(domain: str) -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    ws = WORKSPACE_ROOT / domain / ts
    ws.mkdir(parents=True, exist_ok=True)
    print(f"  Workspace: {ws.relative_to(BASE_DIR)}")
    return ws


def latest_workspace(domain: str) -> Path:
    domain_dir = WORKSPACE_ROOT / domain
    if not domain_dir.exists():
        raise RuntimeError(f"No workspaces found for '{domain}'.")
    candidates = sorted(
        [d for d in domain_dir.iterdir()
         if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_\d{6}", d.name)],
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No workspaces found for '{domain}'.")
    return candidates[0]


def load_state(ws: Path) -> dict:
    sf = ws / "pipeline_state.json"
    if sf.exists():
        return json.loads(sf.read_text())
    return {"completed": [], "failed": [], "domain": None, "voice_id": None}


def save_state(ws: Path, state: dict) -> None:
    (ws / "pipeline_state.json").write_text(json.dumps(state, indent=2))


# ─────────────────────────────────────────────────────────────
# PROMPT FILE RESOLVER
# ─────────────────────────────────────────────────────────────

def resolve_prompt_file(step_id: str, domain: str, prompt_file: str = None) -> Path:
    """
    Find the prompt file for a step in the domain-specific prompts directory.

    If prompt_file is given, load that exact filename — used when step IDs were
    renumbered but prompt filenames were not (e.g. step 10 still uses 08_narration.md).

    Discovery conventions inside prompts/{domain}/ (used when prompt_file is None):
      - NN_name.md   (steps 1–5, e.g. 01_research.md)
      - promptN.md   (legacy, e.g. prompt8.md)
    """
    domain_dir = PROMPTS_DIR / domain
    if not domain_dir.exists():
        raise FileNotFoundError(
            f"No prompt directory for domain '{domain}': {domain_dir}\n"
            f"Create the directory and add prompt files for this domain."
        )

    if prompt_file:
        p = domain_dir / prompt_file
        if not p.exists():
            raise FileNotFoundError(f"Prompt file not found: {p}")
        return p

    for f in domain_dir.iterdir():
        if (re.match(rf"^0*{re.escape(step_id)}[_.]", f.name)
                or f.name == f"prompt{step_id}.md"):
            return f

    raise FileNotFoundError(
        f"No prompt file for step {step_id} in {domain_dir}. "
        f"Files: {sorted(f.name for f in domain_dir.iterdir())}"
    )


# ─────────────────────────────────────────────────────────────
# GEMINI CLIENT
# ─────────────────────────────────────────────────────────────

def _gemini_client():
    try:
        from google import genai
        return genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        print("[ERROR] Missing: pip install google-genai")
        sys.exit(1)


def _is_quota_error(e: Exception) -> bool:
    from google.genai.errors import ClientError
    return isinstance(e, ClientError) and getattr(e, "code", None) == 429


def gemini_generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    client = _gemini_client()
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text
    except Exception as e:
        if _is_quota_error(e) and model == GEMINI_MODEL:
            print(f"\n  [WARN] {GEMINI_MODEL} quota exhausted — falling back to {GEMINI_FALLBACK_MODEL}")
            print(f"  [WARN] Reason: {e}\n")
            return gemini_generate(prompt, model=GEMINI_FALLBACK_MODEL)
        raise


# ─────────────────────────────────────────────────────────────
# STEP RUNNERS
# ─────────────────────────────────────────────────────────────

def run_gemini_step(step: dict, ws: Path, state: dict) -> None:
    domain = state["domain"]
    prompt_file_override = step.get("prompt_file")
    prompt_path = resolve_prompt_file(step["id"], domain, prompt_file_override)
    prompt = prompt_path.read_text()

    for var_name, filename in step.get("inputs", {}).items():
        src = ws / filename
        if not src.exists():
            raise FileNotFoundError(f"Required input missing for step {step['id']}: {src.name}")
        prompt = prompt.replace("{{" + var_name + "}}", src.read_text())

    print(f"  Calling {GEMINI_MODEL} (fallback: {GEMINI_FALLBACK_MODEL})...")
    text = gemini_generate(prompt)

    # Step 16 (Edit Decision List): strip code fences, validate JSON
    if step["id"] == "16":
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        json.loads(text)  # raises ValueError if malformed

    out_path = ws / step["output"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(f"  Saved → {out_path.relative_to(BASE_DIR)}")



def run_elevenlabs_tts(step: dict, ws: Path, state: dict) -> None:
    try:
        import requests
    except ImportError:
        print("[ERROR] Missing: pip install requests")
        sys.exit(1)

    narration_script = (ws / "narration_script.txt").read_text()

    # Extract the clean ElevenLabs-ready section produced by prompt8.md
    marker = "=== ELEVENLABS VERSION ==="
    tts_text = (
        narration_script.split(marker, 1)[1].strip()
        if marker in narration_script
        else narration_script.strip()
    )

    voice_id = state.get("voice_id") or DOMAIN_VOICE_MAP["general_knowledge"]
    print(f"  Voice: {voice_id} | Model: {ELEVENLABS_MODEL}")

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": tts_text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
    )
    response.raise_for_status()

    out_path = ws / "narration.mp3"
    out_path.write_bytes(response.content)
    print(f"  Saved → {out_path.relative_to(BASE_DIR)}")


def run_elevenlabs_music(step: dict, ws: Path, state: dict) -> None:
    try:
        import requests
    except ImportError:
        print("[ERROR] Missing: pip install requests")
        sys.exit(1)

    music_prompt = (ws / "music_prompt.txt").read_text().strip()
    if len(music_prompt) > 450:
        music_prompt = music_prompt[:447] + "..."
        print(f"  [WARN] Music prompt truncated to 450 chars (ElevenLabs limit)")
    print(f"  Generating music ({len(music_prompt)} char prompt)...")

    response = requests.post(
        "https://api.elevenlabs.io/v1/sound-generation",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": music_prompt,
            "duration_seconds": 22,   # ElevenLabs sound-generation max is 22s; loop in assembly
            "prompt_influence": 0.3,
        },
    )
    response.raise_for_status()

    out_path = ws / "music.wav"
    out_path.write_bytes(response.content)
    print(f"  Saved 22s clip → {out_path.relative_to(BASE_DIR)}")

    # Extend to full video length by looping the clip with ffmpeg.
    # Target: 210s (3.5 min) — covers a 3-minute video with buffer.
    # Fade out over the final 10 seconds so it doesn't cut abruptly.
    extended_path = ws / "music_extended.wav"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(out_path),
            "-t", "210",
            "-af", "afade=t=out:st=200:d=10",
            str(extended_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        extended_path.replace(out_path)   # overwrite music.wav with the extended version
        print(f"  Extended to 210s → {out_path.relative_to(BASE_DIR)}")
    else:
        print(f"  [WARN] ffmpeg loop failed — keeping 22s clip. stderr: {result.stderr[-200:]}")


def run_imagen_generation(step: dict, ws: Path, state: dict) -> None:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[ERROR] Missing: pip install google-genai")
        sys.exit(1)

    assets_dir = ws / "assets"
    if not assets_dir.exists():
        print("  No assets/ directory — skipping image generation")
        return

    generated_txts = sorted(assets_dir.rglob("generated.txt"))
    if not generated_txts:
        print("  No generated.txt files found in assets/")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)

    for txt_file in generated_txts:
        out_img = txt_file.parent / "image.png"
        if out_img.exists():
            print(f"  Skip {txt_file.parent.relative_to(ws)} — image.png exists")
            continue

        image_prompt = txt_file.read_text().strip()
        label = txt_file.parent.relative_to(ws)
        print(f"  Generating image: {label}...")

        response = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=image_prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )

        if response.generated_images:
            out_img.write_bytes(response.generated_images[0].image.image_bytes)
            print(f"    → {out_img.relative_to(BASE_DIR)}")
        else:
            print(f"    [WARN] No image returned for {label}")


def _parse_asset_manifest(text: str) -> dict:
    """
    Parse asset_manifest.md into a lookup dict keyed by (scene, asset).
    Handles both 'SCENE X' (single asset per scene → asset defaults to '1')
    and 'SCENE X / ASSET Y' or separate 'ASSET Y' lines.
    Returns: {("1", "1"): {"ken_burns": "zoom_in", "visual_goal": "...", "duration": "5s"}, ...}
    """
    manifest = {}
    for block in text.split("---"):
        block = block.strip()
        if not block:
            continue

        scene = None
        asset = "1"
        ken_burns = ""
        visual_goal = ""
        duration = ""

        for line in block.splitlines():
            stripped = line.strip()
            # "SCENE X / ASSET Y" or "SCENE X"
            if stripped.upper().startswith("SCENE "):
                parts = re.split(r"\s*/\s*", stripped, maxsplit=1)
                scene_part = parts[0].strip()
                scene = scene_part.split()[-1]
                if len(parts) > 1 and parts[1].upper().startswith("ASSET "):
                    asset = parts[1].strip().split()[-1]
            elif stripped.upper().startswith("ASSET "):
                asset = stripped.split()[-1]
            elif stripped.upper().startswith("KEN_BURNS:"):
                ken_burns = stripped.split(":", 1)[1].strip().lower()
            elif stripped.upper().startswith("VISUAL_GOAL:"):
                visual_goal = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("DURATION:"):
                duration = stripped.split(":", 1)[1].strip()

        if scene:
            manifest[(scene, asset)] = {
                "ken_burns": ken_burns,
                "visual_goal": visual_goal,
                "duration": duration,
            }

    return manifest


def run_animation_prompt_step(step: dict, ws: Path, state: dict) -> None:
    """
    Step 8 — For each static asset (image.png / map.png / chart.png), call Gemini
    to write a one-paragraph cinematic animation description → animated.txt.
    Skips assets that already have animated.txt (resumable).
    """
    domain = state["domain"]

    # Load manifest metadata (KEN_BURNS + VISUAL_GOAL per scene/asset)
    manifest_path = ws / "asset_manifest.md"
    manifest = {}
    if manifest_path.exists():
        manifest = _parse_asset_manifest(manifest_path.read_text())

    # Load story excerpt (first ~500 chars) for vibe injection
    story_path = ws / "story_script.md"
    story_excerpt = ""
    if story_path.exists():
        story_excerpt = story_path.read_text()[:500].strip()

    # Load domain animation prompt template
    prompt_template_path = resolve_prompt_file("8", domain)
    prompt_template = prompt_template_path.read_text()

    assets_dir = ws / "assets"
    if not assets_dir.exists():
        print("  No assets/ directory — skipping animation prompts")
        return

    static_files = []
    for candidate in ("image.png", "map.png", "chart.png"):
        static_files.extend(sorted(assets_dir.rglob(candidate)))

    if not static_files:
        print("  No static asset files found — skipping animation prompts")
        return

    processed = 0
    for asset_file in static_files:
        out_txt = asset_file.parent / "animated.txt"
        if out_txt.exists():
            label = asset_file.parent.relative_to(ws)
            print(f"  Skip {label} — animated.txt exists")
            continue

        # Derive scene/asset numbers from folder path (scene_X/asset_Y)
        parts = asset_file.parent.parts
        scene_n = "1"
        asset_n = "1"
        for p in parts:
            if p.startswith("scene_"):
                scene_n = p.split("_", 1)[1]
            elif p.startswith("asset_"):
                asset_n = p.split("_", 1)[1]

        meta = manifest.get((scene_n, asset_n), {})
        ken_burns = meta.get("ken_burns", "zoom_in")
        visual_goal = meta.get("visual_goal", "")
        duration = meta.get("duration", "")

        # Derive asset_type from filename
        name_to_type = {"image.png": "ai_image", "map.png": "map", "chart.png": "chart"}
        asset_type = name_to_type.get(asset_file.name, "image")

        prompt = (
            prompt_template
            .replace("{{ken_burns}}", ken_burns)
            .replace("{{visual_goal}}", visual_goal)
            .replace("{{asset_type}}", asset_type)
            .replace("{{story_excerpt}}", story_excerpt)
            .replace("{{duration}}", duration)
        )

        label = asset_file.parent.relative_to(ws)
        print(f"  Generating animation prompt: {label}...")
        text = gemini_generate(prompt)
        out_txt.write_text(text.strip())
        print(f"    → {out_txt.relative_to(BASE_DIR)}")

        # Write sidecar so Step 9 can read burn key + duration without re-parsing the manifest
        meta_path = asset_file.parent / "asset_meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps({"ken_burns": ken_burns, "duration": duration}, indent=2))

        processed += 1

    if processed == 0:
        print("  All animation prompts already exist — nothing to do")


def run_runpod_animation(step: dict, ws: Path, state: dict) -> None:
    """
    Step 9 — For each animated.txt, submit image + prompt to ComfyUI (RunPod pod) running
    Wan 2.1 I2V and download the resulting animated.mp4.
    Skips assets that already have animated.mp4 (resumable).
    Requires COMFYUI_URL in .keys and wan_i2v_workflow.json at the repo root.
    """
    import time as _time

    try:
        import requests
    except ImportError:
        print("[ERROR] Missing: pip install requests")
        sys.exit(1)

    if not COMFYUI_URL:
        print("  [WARN] COMFYUI_URL is not set — skipping ComfyUI animation")
        print("  Set COMFYUI_URL in .keys and re-run: python automate.py --step 9")
        return

    workflow_path = BASE_DIR / "wan_i2v_workflow.json"
    if not workflow_path.exists():
        print(f"  [ERROR] {workflow_path} not found — cannot run animation")
        return
    workflow_template = workflow_path.read_text()

    assets_dir = ws / "assets"
    if not assets_dir.exists():
        print("  No assets/ directory — skipping ComfyUI animation")
        return

    animated_txts = sorted(assets_dir.rglob("animated.txt"))
    if not animated_txts:
        print("  No animated.txt files found — run step 8 first")
        return

    processed = 0
    for txt_file in animated_txts:
        out_mp4 = txt_file.parent / "animated.mp4"
        if out_mp4.exists():
            label = txt_file.parent.relative_to(ws)
            print(f"  Skip {label} — animated.mp4 exists")
            continue

        # Find the static asset to animate
        static_asset = None
        for candidate in ("image.png", "map.png", "chart.png"):
            candidate_path = txt_file.parent / candidate
            if candidate_path.exists():
                static_asset = candidate_path
                break

        if static_asset is None:
            label = txt_file.parent.relative_to(ws)
            print(f"  [WARN] {label}: no static asset found — skipping")
            continue

        # Read animation prompt
        animation_prompt = txt_file.read_text().strip()

        # Read burn key + duration from sidecar (written by step 8)
        meta_path = txt_file.parent / "asset_meta.json"
        ken_burns = "zoom_in"
        duration = "5 seconds"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            ken_burns = meta.get("ken_burns", ken_burns)
            duration = meta.get("duration", duration)

        # Build final prompt: motion prefix + animation description
        motion_prefix = BURN_KEY_PREFIXES.get(ken_burns, "")
        final_prompt = f"{motion_prefix} {animation_prompt}".strip() if motion_prefix else animation_prompt
        frame_count = _duration_to_frames(duration)

        label = txt_file.parent.relative_to(ws)
        print(f"  Animating {label} ({frame_count} frames @ {COMFYUI_FPS}fps)...")

        try:
            # 1. Upload image to ComfyUI
            with static_asset.open("rb") as img_f:
                upload_resp = requests.post(
                    f"{COMFYUI_URL}/upload/image",
                    files={"image": (static_asset.name, img_f, "image/png")},
                    timeout=30,
                )
            upload_resp.raise_for_status()
            uploaded_filename = upload_resp.json()["name"]

            # 2. Build workflow from template
            workflow_json = (
                workflow_template
                .replace("__IMAGE_FILENAME__", uploaded_filename)
                .replace('"__PROMPT__"', json.dumps(final_prompt))
                .replace("__FRAME_COUNT__", str(frame_count))
            )
            workflow = json.loads(workflow_json)

            # 3. Submit workflow to ComfyUI
            submit_resp = requests.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow},
                timeout=30,
            )
            submit_resp.raise_for_status()
            prompt_id = submit_resp.json()["prompt_id"]
            print(f"    Prompt ID: {prompt_id} — polling...")

            # 4. Poll /history until complete (max 10 minutes)
            output_filename = None
            for attempt in range(120):
                _time.sleep(5)
                history_resp = requests.get(
                    f"{COMFYUI_URL}/history/{prompt_id}",
                    timeout=30,
                )
                history_resp.raise_for_status()
                history = history_resp.json()

                if prompt_id not in history:
                    print(f"    [{attempt+1}/120] Waiting...")
                    continue

                entry = history[prompt_id]
                if not entry.get("status", {}).get("completed", False):
                    status_str = entry.get("status", {}).get("status_str", "processing")
                    print(f"    [{attempt+1}/120] {status_str}...")
                    continue

                # Job complete — find video filename in outputs
                outputs = entry.get("outputs", {})
                for node_output in outputs.values():
                    for key in ("gifs", "videos", "images"):
                        files = node_output.get(key, [])
                        if files:
                            output_filename = files[0].get("filename")
                            break
                    if output_filename:
                        break
                break
            else:
                print(f"    [WARN] Timed out after 10 minutes for {label}")
                continue

            if not output_filename:
                print(f"    [WARN] Job completed but no output file found for {label}")
                continue

            # 5. Download video
            download_resp = requests.get(
                f"{COMFYUI_URL}/view",
                params={"filename": output_filename, "type": "output"},
                timeout=60,
            )
            download_resp.raise_for_status()
            out_mp4.write_bytes(download_resp.content)
            print(f"    → {out_mp4.relative_to(BASE_DIR)}")

        except Exception as exc:
            print(f"  [WARN] ComfyUI call failed for {label}: {exc}")
            continue

        processed += 1

    if processed == 0 and not any(
        (txt.parent / "animated.mp4").exists() for txt in animated_txts
    ):
        print("  No animated.mp4 files produced (check COMFYUI_URL and wan_i2v_workflow.json)")


def _parse_acquisition_doc(text: str) -> list[dict]:
    """Parse asset_acquisition.md into a list of asset dicts."""
    assets = []
    for block in text.split("---"):
        block = block.strip()
        if not block:
            continue

        asset: dict = {}
        key = None
        value_lines: list[str] = []

        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("SCENE "):
                asset["scene"] = stripped.split()[-1]
            elif stripped.startswith("ASSET "):
                asset["asset"] = stripped.split()[-1]
            elif stripped.endswith(":") and stripped.rstrip(":").replace("_", "").isupper():
                if key:
                    asset[key] = "\n".join(value_lines).strip()
                key = stripped.rstrip(":").lower()
                value_lines = []
            elif key:
                value_lines.append(stripped)

        if key:
            asset[key] = "\n".join(value_lines).strip()

        if "scene" in asset and "asset" in asset:
            assets.append(asset)

    return assets


def _fetch_stock(query: str, asset_type: str, out_dir: Path) -> None:
    """Download one stock photo or video from Pexels."""
    try:
        import requests
    except ImportError:
        print("[ERROR] Missing: pip install requests")
        return

    if asset_type == "photo":
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=1"
        headers = {"Authorization": PEXELS_API_KEY}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos:
            print(f"    [WARN] No Pexels photo found for: {query}")
            return
        img_url = photos[0]["src"]["large"]
        content = requests.get(img_url, timeout=60).content
        (out_dir / "image.jpg").write_bytes(content)
        print(f"    → {(out_dir / 'image.jpg').name}")

    elif asset_type == "video":
        url = f"https://api.pexels.com/videos/search?query={query}&per_page=1"
        headers = {"Authorization": PEXELS_API_KEY}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        videos = r.json().get("videos", [])
        if not videos:
            print(f"    [WARN] No Pexels video found for: {query}")
            return
        files = videos[0].get("video_files", [])
        # pick lowest quality to keep download fast
        files_sorted = sorted(files, key=lambda f: f.get("width", 0))
        vid_url = files_sorted[0]["link"]
        content = requests.get(vid_url, timeout=120).content
        (out_dir / "video.mp4").write_bytes(content)
        print(f"    → {(out_dir / 'video.mp4').name}")


def run_fetch_assets(step: dict, ws: Path, state: dict) -> None:
    acquisition_doc = ws / "asset_acquisition.md"
    if not acquisition_doc.exists():
        raise FileNotFoundError("asset_acquisition.md not found — run step 5 first")

    assets = _parse_acquisition_doc(acquisition_doc.read_text())
    if not assets:
        raise ValueError("No assets parsed from asset_acquisition.md")

    print(f"  Parsed {len(assets)} asset(s)")

    for a in assets:
        scene_n  = a.get("scene", "?")
        asset_n  = a.get("asset", "?")
        atype    = a.get("type", "").strip().lower()
        label    = f"scene_{scene_n}/asset_{asset_n}"
        out_dir  = ws / "assets" / f"scene_{scene_n}" / f"asset_{asset_n}"
        out_dir.mkdir(parents=True, exist_ok=True)

        if atype == "ai_video":
            prompt = a.get("ai_prompt", "").strip().strip('"')
            if not prompt or prompt.upper() == "N/A":
                print(f"  [WARN] {label}: no AI prompt, skipping")
                continue
            (out_dir / "generated.txt").write_text(prompt)
            print(f"  {label}: wrote generated.txt ({len(prompt)} chars)")

        elif atype == "map":
            spec = a.get("map_spec", "").strip()
            if not spec or spec.upper() == "N/A":
                print(f"  [WARN] {label}: no map spec, skipping")
                continue
            (out_dir / "map_spec.json").write_text(spec)
            print(f"  {label}: wrote map_spec.json")

        elif atype in ("photo", "video"):
            variations = a.get("search_variations", "").strip()
            if not variations or variations.upper() == "N/A":
                print(f"  [WARN] {label}: no search variations, skipping")
                continue
            query = variations.splitlines()[0].strip()
            print(f"  {label}: fetching {atype} for '{query}'...")
            _fetch_stock(query, atype, out_dir)

        else:
            print(f"  [WARN] {label}: unknown type '{atype}', skipping")


def run_script(step: dict, ws: Path, state: dict) -> None:
    script_path = SCRIPTS_DIR / step["script"]
    if not script_path.exists():
        raise FileNotFoundError(
            f"Script not found: scripts/{step['script']}\n"
            f"Create it before running step {step['id']} ({step['name']})."
        )

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        env={**os.environ, "WORKSPACE_DIR": str(ws), "BASE_DIR": str(BASE_DIR)},
    )
    if result.returncode != 0:
        raise RuntimeError(f"scripts/{step['script']} exited with code {result.returncode}")


# ─────────────────────────────────────────────────────────────
# OUTPUT CHECK
# ─────────────────────────────────────────────────────────────

def output_exists(step: dict, ws: Path) -> bool:
    out = step["output"]
    if out.startswith("output/"):
        return (BASE_DIR / out).exists()
    if out.endswith("/"):
        p = ws / out
        return p.exists() and any(p.rglob("*"))
    return (ws / out).exists()


# ─────────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────────

def dispatch(step: dict, ws: Path, state: dict) -> None:
    t = step["type"]
    if t == "gemini":
        run_gemini_step(step, ws, state)
    elif t == "imagen":
        run_imagen_generation(step, ws, state)
    elif t == "animation_prompt":
        run_animation_prompt_step(step, ws, state)
    elif t == "runpod_animation":
        run_runpod_animation(step, ws, state)
    elif t == "tts":
        run_elevenlabs_tts(step, ws, state)
    elif t == "music":
        run_elevenlabs_music(step, ws, state)
    elif t == "fetch_assets":
        run_fetch_assets(step, ws, state)
    elif t == "script":
        run_script(step, ws, state)
    else:
        raise ValueError(f"Unknown step type: {t}")


def execute_step(step: dict, ws: Path, state: dict, force: bool = False) -> bool:
    sid = step["id"]

    if not force and output_exists(step, ws):
        print(f"  [SKIP] Step {sid}: {step['name']} — output exists")
        return True

    print(f"\n{'─'*60}")
    print(f"  Step {sid}: {step['name']}")
    print(f"{'─'*60}")

    try:
        dispatch(step, ws, state)

        state["completed"] = list(dict.fromkeys([*state["completed"], sid]))
        state["failed"] = [x for x in state["failed"] if x != sid]
        save_state(ws, state)
        print(f"  [OK] Step {sid} complete")
        return True

    except Exception as exc:
        if sid not in state["failed"]:
            state["failed"].append(sid)
        save_state(ws, state)
        print(f"  [FAIL] Step {sid}: {exc}")
        return False


# ─────────────────────────────────────────────────────────────
# STATUS DISPLAY
# ─────────────────────────────────────────────────────────────

def show_status(ws: Path) -> None:
    state = load_state(ws)
    print(f"\n{'='*65}")
    print(f"  PIPELINE STATUS — {ws.name}")
    print(f"  Domain : {state.get('domain') or 'not classified'}")
    print(f"  Voice  : {state.get('voice_id') or 'not selected'}")
    print(f"{'='*65}\n")
    for step in STEPS:
        exists = output_exists(step, ws)
        sid = step["id"]
        failed = sid in state.get("failed", [])
        icon = "[+]" if exists else ("[!]" if failed else "[ ]")
        print(f"  {icon} Step {sid:<3s}  {step['name']:<35s}  {step['type']}")
    print(f"\n  [+] done   [ ] pending   [!] failed")
    print(f"{'='*65}\n")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Vid Life automated pipeline")
    parser.add_argument("--step",   help="Run a single step by ID (e.g. 3 or 12b)")
    parser.add_argument("--status", action="store_true", help="Show status of latest workspace")
    args = parser.parse_args()

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

    if args.status:
        domain = select_domain()
        try:
            show_status(latest_workspace(domain))
        except RuntimeError as e:
            print(f"  {e}")
        return

    if args.step:
        domain = select_domain()
        try:
            ws = latest_workspace(domain)
        except RuntimeError as e:
            print(f"  {e}")
            sys.exit(1)
        state = load_state(ws)
        step = next((s for s in STEPS if s["id"] == args.step), None)
        if not step:
            print(f"Unknown step: {args.step}. Valid IDs: {[s['id'] for s in STEPS]}")
            sys.exit(1)
        execute_step(step, ws, state, force=True)
        return

    # Full pipeline — resume latest workspace for domain or start fresh
    domain = select_domain()
    try:
        ws = latest_workspace(domain)
        state = load_state(ws)
        print(f"  Resuming workspace: {ws.relative_to(BASE_DIR)}\n")
    except RuntimeError:
        ws = new_workspace(domain)
        state = {"completed": [], "failed": [], "domain": domain, "voice_id": DOMAIN_VOICE_MAP[domain]}
        save_state(ws, state)
        print(f"  No previous workspace for '{domain}' — starting fresh.\n")

    print("  Starting pipeline...\n")

    for step in STEPS:
        execute_step(step, ws, state)

    failed = state.get("failed", [])
    done = len(state.get("completed", []))
    print(f"\n{'='*60}")
    print(f"  Domain   : {domain}")
    print(f"  Done     : {done} steps  |  Failed: {len(failed)}")
    if failed:
        print(f"  Failed steps: {', '.join(failed)}")
        print(f"  Retry with: python automate.py --step <id>")
    print(f"  Workspace: {ws.relative_to(BASE_DIR)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
