"""
backend/tasks.py — VidLife pipeline exposed as FastAPI endpoints.

Independent implementation — does not import automate.py.
Mounted at /tasks in backend/server.py.
"""

import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import cost_estimate


# ─────────────────────────────────────────────────────────────
# API Keys — loaded from settings.json (managed via Settings UI)
# ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    """Return current settings, re-read on every call so live edits take effect."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import settings as _s
    return _s.load()

def GEMINI_API_KEY()     -> str:  return _cfg().get("GEMINI_API_KEY", "")
def ELEVENLABS_API_KEY() -> str:  return _cfg().get("ELEVENLABS_API_KEY", "")
def PEXELS_API_KEY()     -> str:  return _cfg().get("PEXELS_API_KEY", "")
def PIXABAY_API_KEY()    -> str:  return _cfg().get("PIXABAY_API_KEY", "")
def RUNPOD_URL()         -> str:  return _cfg().get("RUNPOD_URL", "").rstrip("/")
def OPENROUTER_API_KEY() -> str:  return _cfg().get("OPENROUTER_API_KEY", "")
def USE_OPENROUTER()     -> bool: return bool(_cfg().get("USE_OPENROUTER", False))
def MOCK_AI()            -> bool: return bool(_cfg().get("MOCK_AI", False))
def ENABLE_FULL_PIPELINE() -> bool: return bool(_cfg().get("ENABLE_FULL_PIPELINE", False))


# ─────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────

GEMINI_MODEL          = "gemini-2.5-pro"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"
IMAGEN_MODEL          = "imagen-4.0-generate-001"
ELEVENLABS_MODEL      = "eleven_v3"


# ─────────────────────────────────────────────────────────────
# Paths — project root is two levels up from this file
# ─────────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).parent.parent
PROMPTS_DIR    = BASE_DIR / "prompts"
SCRIPTS_DIR    = BASE_DIR / "scripts"
WORKSPACE_ROOT = BASE_DIR / "workspace"


# ─────────────────────────────────────────────────────────────
# Domain config
# ─────────────────────────────────────────────────────────────

DOMAIN_VOICE_MAP = {
    "political":         "pNInz6obpgDQGcFmaJgB",
    "general_knowledge": "onwK4e9ZLuTAKqWW03F9",
    "science":           "N2lVS1w4EtoT3dr4eOWO",
    "business":          "XB0fDUnXU5powFXDhCwa",
    "history":           "IKne3meq5aSn9XLyUdCD",
    "sports":            "ErXwobaYiN019PkySvjV",
    "technology":        "pqHfZKP75CvOlQylNhV4",
    "general":           "pqHfZKP75CvOlQylNhV4",
}

SUPPORTED_DOMAINS = list(DOMAIN_VOICE_MAP.keys())

BURN_KEY_PREFIXES = {
    "zoom_in":   "slow push in,",
    "zoom_out":  "slow pull back,",
    "pan_left":  "camera pan left,",
    "pan_right": "camera pan right,",
}


# ─────────────────────────────────────────────────────────────
# Step definitions
# ─────────────────────────────────────────────────────────────

STEPS = [
    {"id": "1",  "name": "Research",                      "type": "gemini",           "inputs": {},                                                              "output": "research_dossier.md"},
    {"id": "2",  "name": "Story Script",                  "type": "gemini",           "inputs": {"research_dossier": "research_dossier.md"},                     "output": "story_script.md"},
    {"id": "3",  "name": "Scene Breakdown",               "type": "gemini",           "inputs": {"story_script": "story_script.md"},                             "output": "scene_plan.md"},
    {"id": "4",  "name": "Asset Manifest",                "type": "gemini",           "inputs": {"scene_plan": "scene_plan.md"},                                 "output": "asset_manifest.md"},
    {"id": "5",  "name": "Asset Acquisition Instructions","type": "gemini",           "inputs": {"asset_manifest": "asset_manifest.md"},                         "output": "asset_acquisition.md"},
    {"id": "6",  "name": "Fetch Assets",                  "type": "fetch_assets",     "output": "assets/"},
    {"id": "7",  "name": "AI Image Generation",           "type": "imagen",           "output": "assets/"},
    {"id": "8",  "name": "Animation Prompt",              "type": "animation_prompt", "output": "assets/", "output_marker": "animated.txt"},
    {"id": "9",  "name": "Video Animation",               "type": "runpod_animation", "output": "assets/", "output_marker": "animated.mp4"},
    {"id": "10", "name": "Narration Script",              "type": "gemini",           "inputs": {"story_script": "story_script.md"},                             "output": "narration_script.txt", "prompt_file": "10_narration.md"},
    {"id": "11", "name": "Narration Audio",               "type": "tts",              "output": "narration.mp3"},
    {"id": "12", "name": "Music Prompt",                  "type": "gemini",           "inputs": {"scene_plan": "scene_plan.md"},                                 "output": "music_prompt.txt"},
    {"id": "13", "name": "Music Audio",                   "type": "music",            "output": "music.wav"},
    {"id": "14", "name": "Asset Inventory",               "type": "script",           "script": "generate_inventory.py",                                         "output": "asset_inventory.txt"},
    {"id": "15", "name": "Narration Timing",              "type": "script",           "script": "analyze_timing.py",                                             "output": "narration_timing.json"},
    {"id": "16", "name": "Edit Decision List",            "type": "gemini",           "inputs": {"asset_inventory": "asset_inventory.txt", "narration_timing": "narration_timing.json"}, "output": "edl.json"},
    {"id": "17", "name": "Final Assembly",                "type": "script",           "script": "assemble.py",                                                   "output": "output/final_video.mp4"},
    {"id": "18", "name": "Platform Metadata",             "type": "gemini",           "prompt_file": "02b_platform_metadata.md", "inputs": {"research_dossier": "research_dossier.md", "story_script": "story_script.md"}, "output": "platform_metadata.json"},
]

STEPS_BY_ID: dict = {s["id"]: s for s in STEPS}


# ─────────────────────────────────────────────────────────────
# Active run tracking (in-memory)
# ─────────────────────────────────────────────────────────────

_active_runs: Dict[str, dict] = {}
_active_runs_lock = threading.Lock()


def _run_key(domain: str, run_id: str) -> str:
    return f"{domain}/{run_id}"


def _mark_active(domain: str, run_id: str, step_id: Optional[str]) -> None:
    with _active_runs_lock:
        _active_runs[_run_key(domain, run_id)] = {
            "step_id": step_id,
            "status": "running",
        }


def _mark_idle(domain: str, run_id: str) -> None:
    with _active_runs_lock:
        _active_runs.pop(_run_key(domain, run_id), None)


def _get_active(domain: str, run_id: str) -> Optional[dict]:
    with _active_runs_lock:
        return _active_runs.get(_run_key(domain, run_id))


def _is_active(domain: str, run_id: str) -> bool:
    return _get_active(domain, run_id) is not None


# ─────────────────────────────────────────────────────────────
# Workspace helpers
# ─────────────────────────────────────────────────────────────

def new_workspace(domain: str) -> tuple[str, Path]:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    ws = WORKSPACE_ROOT / domain / ts
    ws.mkdir(parents=True, exist_ok=True)
    return ts, ws


def latest_workspace(domain: str) -> tuple[str, Path]:
    domain_dir = WORKSPACE_ROOT / domain
    if not domain_dir.exists():
        raise RuntimeError(f"No workspaces found for domain '{domain}'")
    candidates = sorted(
        [d for d in domain_dir.iterdir() if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}_\d{6}", d.name)],
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No workspaces found for domain '{domain}'")
    return candidates[0].name, candidates[0]


def find_workspace(domain: str, run_id: str) -> Path:
    ws = WORKSPACE_ROOT / domain / run_id
    if not ws.exists() or not ws.is_dir():
        raise RuntimeError(f"No workspace found for run_id '{run_id}' in domain '{domain}'")
    return ws


def load_state(ws: Path) -> dict:
    sf = ws / "pipeline_state.json"
    if sf.exists():
        return json.loads(sf.read_text())
    return {"completed": [], "failed": [], "domain": None, "voice_id": None}


def save_state(ws: Path, state: dict) -> None:
    (ws / "pipeline_state.json").write_text(json.dumps(state, indent=2))


# ─────────────────────────────────────────────────────────────
# Prompt resolver
# ─────────────────────────────────────────────────────────────

def resolve_prompt_file(step_id: str, domain: str, prompt_file: Optional[str] = None) -> Path:
    domain_dir = PROMPTS_DIR / domain
    if not domain_dir.exists():
        raise FileNotFoundError(f"No prompt directory for domain '{domain}': {domain_dir}")

    if prompt_file:
        p = domain_dir / prompt_file
        if not p.exists():
            raise FileNotFoundError(f"Prompt file not found: {p}")
        return p

    for f in domain_dir.iterdir():
        if re.match(rf"^0*{re.escape(step_id)}[_.]", f.name) or f.name == f"prompt{step_id}.md":
            return f

    raise FileNotFoundError(
        f"No prompt file for step {step_id} in {domain_dir}. "
        f"Files: {sorted(f.name for f in domain_dir.iterdir())}"
    )


# ─────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────

_FIXTURES_DIR = Path(__file__).parent / "mocks" / "fixtures"

_FIXTURE_MAP: dict = {
    "1":  "research_dossier.md",
    "2":  "story_script.md",
    "3":  "scene_plan.md",
    "4":  "asset_manifest.md",
    "5":  "asset_acquisition.md",
    "8":  "animation_prompt_template.txt",
    "10": "narration_script.txt",
    "12": "music_prompt.txt",
    "16": "edl.json",
    "18": "platform_metadata.json",
}


def _load_fixture(step_id: str) -> str:
    fname = _FIXTURE_MAP.get(step_id)
    if not fname:
        return f"[MOCK] No fixture defined for step {step_id}"
    fp = _FIXTURES_DIR / fname
    if not fp.exists():
        return f"[MOCK] Fixture file missing: {fp}"
    return fp.read_text()


# ─────────────────────────────────────────────────────────────
# Gemini client
# ─────────────────────────────────────────────────────────────

def _gemini_generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    if USE_OPENROUTER():
        from open_router.text import generate_text
        return generate_text(prompt, api_key=OPENROUTER_API_KEY())

    try:
        from google import genai
    except ImportError:
        raise RuntimeError("Missing dependency: pip install google-genai")

    client = genai.Client(api_key=GEMINI_API_KEY())
    try:
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text
    except Exception as e:
        from google.genai.errors import ClientError
        if isinstance(e, ClientError) and getattr(e, "code", None) == 429 and model == GEMINI_MODEL:
            return _gemini_generate(prompt, model=GEMINI_FALLBACK_MODEL)
        raise


# ─────────────────────────────────────────────────────────────
# Step runners
# ─────────────────────────────────────────────────────────────

def _run_gemini_step(step: dict, ws: Path, state: dict) -> None:
    if MOCK_AI():
        out_path = ws / step["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_load_fixture(step["id"]))
        return

    domain = state["domain"]
    prompt_path = resolve_prompt_file(step["id"], domain, step.get("prompt_file"))
    prompt = prompt_path.read_text()

    for var_name, filename in step.get("inputs", {}).items():
        src = ws / filename
        if not src.exists():
            raise FileNotFoundError(f"Required input missing for step {step['id']}: {src.name}")
        prompt = prompt.replace("{{" + var_name + "}}", src.read_text())

    if step["id"] == "3":
        video_config = state.get("video_config") or {}
        duration_min = video_config.get("duration_min_minutes", 2)
        duration_max = video_config.get("duration_max_minutes", 30)
        video_split_percent = video_config.get("video_split_percent", 25)
        duration_range = f"between {duration_min} and {duration_max} minutes"
        prompt = prompt.replace("{{duration_range}}", duration_range)
        prompt = prompt.replace("{{video_split_percent}}", str(video_split_percent))

    text = _gemini_generate(prompt)

    if step["id"] == "16":
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text.strip())
        json.loads(text)

    out_path = ws / step["output"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)


def _parse_acquisition_doc(text: str) -> list:
    assets: list = []
    asset: dict = {}
    key: Optional[str] = None
    value_lines: list = []

    def flush_key():
        nonlocal key, value_lines
        if key is not None and asset:
            asset[key] = "\n".join(value_lines).strip()
        key = None
        value_lines.clear()

    def flush_asset():
        flush_key()
        if "scene" in asset and "asset" in asset:
            assets.append(dict(asset))
        asset.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("SCENE "):
            if "scene" in asset:
                flush_asset()
            flush_key()
            asset["scene"] = stripped.split()[-1]
        elif stripped.startswith("ASSET "):
            flush_key()
            asset["asset"] = stripped.split()[-1]
        else:
            m = re.match(r'^([A-Z][A-Z_]+):\s*(.*)$', stripped)
            if m:
                flush_key()
                key = m.group(1).lower()
                inline = m.group(2).strip()
                if inline:
                    value_lines = [inline]
            elif key is not None:
                value_lines.append(stripped)

    flush_asset()
    return assets


def _run_fetch_assets(step: dict, ws: Path, state: dict) -> None:
    acquisition_doc = ws / "asset_acquisition.md"
    if not acquisition_doc.exists():
        raise FileNotFoundError("asset_acquisition.md not found — run step 5 first")

    assets = _parse_acquisition_doc(acquisition_doc.read_text())
    if not assets:
        raise ValueError("No assets parsed from asset_acquisition.md")

    mock = MOCK_AI()
    if mock:
        from mocks.generators import generate_placeholder_image, generate_placeholder_video
        animation_template = _load_fixture("8")

    for a in assets:
        scene_n = a.get("scene", "?")
        asset_n = a.get("asset", "?")
        atype   = a.get("type", "").strip().lower()
        out_dir = ws / "assets" / f"scene_{scene_n}" / f"asset_{asset_n}"
        out_dir.mkdir(parents=True, exist_ok=True)

        if atype in ("ai_video", "ai_image"):
            prompt = a.get("ai_prompt", "").strip().strip('"')
            if prompt and prompt.upper() != "N/A":
                (out_dir / "generated.txt").write_text(prompt)
            if mock:
                generate_placeholder_image(out_dir / "image.png")

        elif atype in ("real_image", "image"):
            query = (
                a.get("search_query", "").strip()
                if atype == "real_image"
                else (a.get("search_variations", "").strip().splitlines() or [""])[0]
                     .strip().lstrip("0123456789. ").strip("\"'")
            )
            if query and query.upper() != "N/A":
                (out_dir / "search_query.txt").write_text(query)
            if mock:
                generate_placeholder_image(out_dir / "image.jpg")

        elif atype == "map":
            spec = a.get("map_spec", "").strip()
            if spec and spec.upper() != "N/A":
                (out_dir / "map_spec.json").write_text(spec)
            if mock:
                generate_placeholder_image(out_dir / "image.png")

        elif atype == "chart":
            spec = a.get("chart_spec", "").strip()
            if spec and spec.upper() != "N/A":
                (out_dir / "chart_spec.json").write_text(spec)
            if mock:
                generate_placeholder_image(out_dir / "image.png")

        if mock:
            (out_dir / "animated.txt").write_text(animation_template)
            (out_dir / "asset_meta.json").write_text(
                json.dumps({"ken_burns": "zoom_in", "duration": "5 seconds"}, indent=2)
            )
            generate_placeholder_video(out_dir / "animated.mp4", duration_seconds=5.0)


def _save_if_valid(img_url: str, out_img: Path) -> bool:
    import requests
    headers = {"User-Agent": "VidLifePipeline/1.0"}
    resp = requests.get(img_url, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.content
    if not data:
        return False
    ct = resp.headers.get("Content-Type", "")
    if "html" in ct or "svg" in ct:
        return False
    if not (data[:3] == b'\xff\xd8\xff' or data[:4] == b'\x89PNG'):
        return False
    out_img.write_bytes(data)
    return True


def _fetch_real_image(query: str, out_dir: Path) -> bool:
    if MOCK_AI():
        from mocks.generators import generate_placeholder_image
        generate_placeholder_image(out_dir / "image.jpg")
        return True

    import requests
    headers = {"User-Agent": "VidLifePipeline/1.0"}
    out_img = out_dir / "image.jpg"

    # 1. Wikipedia
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "titles": query, "prop": "pageimages",
                    "format": "json", "pithumbsize": 1200, "pilicense": "any"},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        for page in r.json().get("query", {}).get("pages", {}).values():
            img_url = page.get("thumbnail", {}).get("source")
            if img_url and _save_if_valid(img_url, out_img):
                return True
    except Exception:
        pass

    time.sleep(1)

    # 2. Wikimedia Commons
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query,
                    "srnamespace": "6", "srlimit": "5", "format": "json"},
            headers=headers, timeout=30,
        )
        r.raise_for_status()
        for result in r.json().get("query", {}).get("search", []):
            time.sleep(0.5)
            fr = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params={"action": "query", "titles": result["title"], "prop": "imageinfo",
                        "iiprop": "url", "iiurlwidth": 1200, "format": "json"},
                headers=headers, timeout=30,
            )
            fr.raise_for_status()
            for fp in fr.json().get("query", {}).get("pages", {}).values():
                info = (fp.get("imageinfo") or [{}])[0]
                img_url = info.get("thumburl") or info.get("url")
                if img_url and _save_if_valid(img_url, out_img):
                    return True
    except Exception:
        pass

    # 3. Pexels fallback
    try:
        r = requests.get(
            f"https://api.pexels.com/v1/search?query={query}&per_page=1",
            headers={"Authorization": PEXELS_API_KEY()}, timeout=30,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if photos and _save_if_valid(photos[0]["src"]["large"], out_img):
            return True
    except Exception:
        pass

    return False


def _run_imagen_generation(step: dict, ws: Path, state: dict, clean: bool = False) -> None:
    if MOCK_AI():
        from mocks.generators import generate_placeholder_image

        assets_dir = ws / "assets"
        if not assets_dir.exists():
            return
        for sq_file in sorted(assets_dir.rglob("search_query.txt")):
            out_img = sq_file.parent / "image.jpg"
            if not out_img.exists():
                generate_placeholder_image(out_img)
        for txt_file in sorted(assets_dir.rglob("generated.txt")):
            out_img = txt_file.parent / "image.png"
            if not out_img.exists():
                generate_placeholder_image(out_img)
        return

    assets_dir = ws / "assets"
    if not assets_dir.exists():
        return

    if clean:
        for pattern in ("image.png", "image.jpg", "blocked.txt"):
            for f in assets_dir.rglob(pattern):
                f.unlink()

    # Web-fetch pass
    for sq_file in sorted(assets_dir.rglob("search_query.txt")):
        out_img = sq_file.parent / "image.jpg"
        if out_img.exists():
            continue
        _fetch_real_image(sq_file.read_text().strip(), sq_file.parent)

    # Imagen pass
    generated_txts = sorted(assets_dir.rglob("generated.txt"))
    if not generated_txts:
        return

    if USE_OPENROUTER():
        from open_router.image import generate_image
        api_key = OPENROUTER_API_KEY()
        for txt_file in generated_txts:
            out_img = txt_file.parent / "image.png"
            if out_img.exists():
                continue
            blocked_marker = txt_file.parent / "blocked.txt"
            if blocked_marker.exists():
                continue
            image_prompt = txt_file.read_text().strip()
            try:
                out_img.write_bytes(generate_image(image_prompt, api_key=api_key))
            except Exception as e:
                blocked_marker.write_text(str(e))
        return

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("Missing dependency: pip install google-genai")

    client = genai.Client(api_key=GEMINI_API_KEY())

    for txt_file in generated_txts:
        out_img = txt_file.parent / "image.png"
        if out_img.exists():
            continue
        blocked_marker = txt_file.parent / "blocked.txt"
        if blocked_marker.exists():
            continue
        image_prompt = txt_file.read_text().strip()
        try:
            response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=image_prompt,
                config=types.GenerateImagesConfig(number_of_images=1),
            )
            if response.generated_images:
                out_img.write_bytes(response.generated_images[0].image.image_bytes)
            else:
                reason = getattr(response, "rai_filtered_reason", None) or "safety filter"
                blocked_marker.write_text(reason)
        except Exception:
            pass


def _parse_asset_manifest(text: str) -> dict:
    manifest = {}
    for block in text.split("---"):
        block = block.strip()
        if not block:
            continue
        scene = asset = None
        asset = "1"
        ken_burns = visual_goal = duration = ""
        animate = "yes"
        for line in block.splitlines():
            s = line.strip()
            if s.upper().startswith("SCENE "):
                parts = re.split(r"\s*/\s*", s, maxsplit=1)
                scene = parts[0].strip().split()[-1]
                if len(parts) > 1 and parts[1].upper().startswith("ASSET "):
                    asset = parts[1].strip().split()[-1]
            elif s.upper().startswith("ASSET "):
                asset = s.split()[-1]
            elif s.upper().startswith("KEN_BURNS:"):
                ken_burns = s.split(":", 1)[1].strip().lower()
            elif s.upper().startswith("VISUAL_GOAL:"):
                visual_goal = s.split(":", 1)[1].strip()
            elif s.upper().startswith("DURATION:"):
                duration = s.split(":", 1)[1].strip()
            elif s.upper().startswith("ANIMATE:"):
                animate = s.split(":", 1)[1].strip().lower()
        if scene:
            manifest[(scene, asset)] = {
                "ken_burns": ken_burns,
                "visual_goal": visual_goal,
                "duration": duration,
                "animate": animate,
            }
    return manifest


def _run_animation_prompt_step(step: dict, ws: Path, state: dict, clean: bool = False) -> None:
    if MOCK_AI():
        assets_dir = ws / "assets"
        if not assets_dir.exists():
            return
        template = _load_fixture("8")
        for candidate in ("image.png", "image.jpg", "map.png", "chart.png"):
            for asset_file in sorted(assets_dir.rglob(candidate)):
                out_txt = asset_file.parent / "animated.txt"
                if not out_txt.exists():
                    out_txt.write_text(template)
                meta_path = asset_file.parent / "asset_meta.json"
                if not meta_path.exists():
                    meta_path.write_text(json.dumps({"ken_burns": "zoom_in", "duration": "5 seconds"}, indent=2))
        return

    domain = state["domain"]
    manifest_path = ws / "asset_manifest.md"
    manifest = _parse_asset_manifest(manifest_path.read_text()) if manifest_path.exists() else {}

    story_path = ws / "story_script.md"
    story_excerpt = story_path.read_text()[:500].strip() if story_path.exists() else ""

    prompt_template = resolve_prompt_file("8", domain).read_text()

    assets_dir = ws / "assets"
    if not assets_dir.exists():
        return

    if clean:
        for pattern in ("animated.txt", "animation_blocked.txt"):
            for f in assets_dir.rglob(pattern):
                f.unlink()

    static_files = []
    for candidate in ("image.png", "image.jpg", "map.png", "chart.png"):
        static_files.extend(sorted(assets_dir.rglob(candidate)))

    for asset_file in static_files:
        out_txt = asset_file.parent / "animated.txt"
        if out_txt.exists():
            continue

        blocked_marker = asset_file.parent / "animation_blocked.txt"
        if blocked_marker.exists():
            continue

        parts = asset_file.parent.parts
        scene_n = asset_n = "1"
        for p in parts:
            if p.startswith("scene_"):
                scene_n = p.split("_", 1)[1]
            elif p.startswith("asset_"):
                asset_n = p.split("_", 1)[1]

        meta = manifest.get((scene_n, asset_n), {})
        ken_burns  = meta.get("ken_burns", "zoom_in")
        visual_goal = meta.get("visual_goal", "")
        duration   = meta.get("duration", "")
        animate    = meta.get("animate", "yes")

        if animate == "no":
            continue

        name_to_type = {"image.png": "ai_image", "image.jpg": "real_image", "map.png": "map", "chart.png": "chart"}
        asset_type = name_to_type.get(asset_file.name, "image")

        prompt = (
            prompt_template
            .replace("{{ken_burns}}", ken_burns)
            .replace("{{visual_goal}}", visual_goal)
            .replace("{{asset_type}}", asset_type)
            .replace("{{story_excerpt}}", story_excerpt)
            .replace("{{duration}}", duration)
        )

        try:
            text = _gemini_generate(prompt)
        except Exception as e:
            blocked_marker.write_text(str(e))
            continue
        out_txt.write_text(text.strip())

        meta_path = asset_file.parent / "asset_meta.json"
        if not meta_path.exists():
            meta_path.write_text(json.dumps({"ken_burns": ken_burns, "duration": duration}, indent=2))


def _duration_to_seconds(duration_str: str) -> int:
    match = re.search(r"(\d+(?:\.\d+)?)", duration_str or "5")
    return max(1, int(float(match.group(1)) if match else 5.0))


def _resolve_animation_inputs(txt_file: Path) -> Optional[tuple]:
    """Return (static_asset, final_prompt, duration_seconds) for an animated.txt
    file, or None if no static asset is found."""
    static_asset = None
    for candidate in ("image.png", "image.jpg", "map.png", "chart.png"):
        p = txt_file.parent / candidate
        if p.exists():
            static_asset = p
            break

    if static_asset is None:
        return None

    animation_prompt = txt_file.read_text().strip()
    meta_path = txt_file.parent / "asset_meta.json"
    ken_burns = "zoom_in"
    duration  = "5 seconds"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        ken_burns = meta.get("ken_burns", ken_burns)
        duration  = meta.get("duration", duration)

    motion_prefix = BURN_KEY_PREFIXES.get(ken_burns, "")
    final_prompt = f"{motion_prefix} {animation_prompt}".strip() if motion_prefix else animation_prompt
    duration_seconds = _duration_to_seconds(duration)

    return static_asset, final_prompt, duration_seconds


def _animate_single_asset(txt_file: Path) -> Path:
    """Animate a single asset from its animated.txt prompt file.

    Returns the path to the written animated.mp4. Raises on failure (no static
    asset found, missing config, or backend error) — callers that want
    best-effort batch behavior should catch exceptions themselves.
    """
    out_mp4 = txt_file.parent / "animated.mp4"

    if MOCK_AI():
        from mocks.generators import generate_placeholder_video
        generate_placeholder_video(out_mp4, duration_seconds=5.0)
        return out_mp4

    resolved = _resolve_animation_inputs(txt_file)
    if resolved is None:
        raise RuntimeError("No static asset (image/map/chart) found for this animation prompt")
    static_asset, final_prompt, duration_seconds = resolved

    if USE_OPENROUTER():
        from open_router.video import generate_video
        api_key = OPENROUTER_API_KEY()
        out_mp4.write_bytes(
            generate_video(static_asset, final_prompt, api_key=api_key, duration_seconds=duration_seconds)
        )
        return out_mp4

    import requests as _requests

    url = RUNPOD_URL()
    if not url:
        raise RuntimeError("RUNPOD_URL is not configured")

    with static_asset.open("rb") as img_f:
        submit_resp = _requests.post(
            f"{url}/generate",
            files={"image": (static_asset.name, img_f, "image/png")},
            data={"prompt": final_prompt, "duration_seconds": duration_seconds},
            timeout=30,
        )
    submit_resp.raise_for_status()
    job_id = submit_resp.json()["job_id"]

    job_status = None
    for _ in range(120):
        time.sleep(5)
        status_resp = _requests.get(f"{url}/status/{job_id}", timeout=30)
        status_resp.raise_for_status()
        job_status = status_resp.json()["status"]
        if job_status in ("done", "failed"):
            break

    if job_status != "done":
        raise RuntimeError(f"Animation job did not complete (status={job_status})")

    download_resp = _requests.get(f"{url}/download/{job_id}", timeout=120, stream=True)
    download_resp.raise_for_status()
    with out_mp4.open("wb") as f:
        for chunk in download_resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    return out_mp4


def _run_runpod_animation(step: dict, ws: Path, state: dict) -> None:
    assets_dir = ws / "assets"
    if not assets_dir.exists():
        return

    for txt_file in sorted(assets_dir.rglob("animated.txt")):
        out_mp4 = txt_file.parent / "animated.mp4"
        if out_mp4.exists():
            continue
        try:
            _animate_single_asset(txt_file)
        except Exception:
            continue


def _run_elevenlabs_tts(step: dict, ws: Path, state: dict) -> None:
    if MOCK_AI():
        from mocks.generators import generate_silent_audio
        generate_silent_audio(ws / "narration.mp3", duration_seconds=10.0, fmt="mp3")
        return

    narration_script = (ws / "narration_script.txt").read_text()
    marker = "=== ELEVENLABS VERSION ==="
    tts_text = (
        narration_script.split(marker, 1)[1].strip()
        if marker in narration_script
        else narration_script.strip()
    )

    if USE_OPENROUTER():
        from open_router.speech import generate_speech
        (ws / "narration.mp3").write_bytes(generate_speech(tts_text, api_key=OPENROUTER_API_KEY()))
        return

    import requests as _requests

    voice_id = state.get("voice_id") or DOMAIN_VOICE_MAP["general_knowledge"]
    response = _requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": ELEVENLABS_API_KEY(), "Content-Type": "application/json"},
        json={"text": tts_text, "model_id": ELEVENLABS_MODEL,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
    )
    response.raise_for_status()
    (ws / "narration.mp3").write_bytes(response.content)


def _run_elevenlabs_music(step: dict, ws: Path, state: dict) -> None:
    if MOCK_AI():
        from mocks.generators import generate_silent_audio
        generate_silent_audio(ws / "music.wav", duration_seconds=22.0, fmt="wav")
        return

    music_prompt = (ws / "music_prompt.txt").read_text().strip()
    if len(music_prompt) > 450:
        music_prompt = music_prompt[:447] + "..."

    out_path = ws / "music.wav"

    if USE_OPENROUTER():
        from open_router.music import generate_music
        out_path.write_bytes(generate_music(music_prompt, api_key=OPENROUTER_API_KEY(), duration_seconds=22))
    else:
        import requests as _requests
        response = _requests.post(
            "https://api.elevenlabs.io/v1/sound-generation",
            headers={"xi-api-key": ELEVENLABS_API_KEY(), "Content-Type": "application/json"},
            json={"text": music_prompt, "duration_seconds": 22, "prompt_influence": 0.3},
        )
        response.raise_for_status()
        out_path.write_bytes(response.content)

    extended_path = ws / "music_extended.wav"
    result = subprocess.run(
        ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(out_path),
         "-t", "210", "-af", "afade=t=out:st=200:d=10", str(extended_path)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        extended_path.replace(out_path)


def _run_script(step: dict, ws: Path, state: dict) -> None:
    script_path = SCRIPTS_DIR / step["script"]
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: scripts/{step['script']}")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        env={**os.environ, "WORKSPACE_DIR": str(ws), "BASE_DIR": str(BASE_DIR)},
    )
    if result.returncode != 0:
        raise RuntimeError(f"scripts/{step['script']} exited with code {result.returncode}")


# ─────────────────────────────────────────────────────────────
# Pipeline execution
# ─────────────────────────────────────────────────────────────

def _output_exists(step: dict, ws: Path) -> bool:
    out = step["output"]
    if out.startswith("output/"):
        return (BASE_DIR / out).exists()
    if out.endswith("/"):
        p = ws / out
        marker = step.get("output_marker")
        if marker:
            return p.exists() and any(p.rglob(marker))
        return p.exists() and any(p.rglob("*"))
    return (ws / out).exists()


def _dispatch(step: dict, ws: Path, state: dict, clean: bool = False) -> None:
    t = step["type"]
    if t == "gemini":
        _run_gemini_step(step, ws, state)
    elif t == "imagen":
        _run_imagen_generation(step, ws, state, clean)
    elif t == "animation_prompt":
        _run_animation_prompt_step(step, ws, state, clean)
    elif t == "runpod_animation":
        _run_runpod_animation(step, ws, state)
    elif t == "tts":
        _run_elevenlabs_tts(step, ws, state)
    elif t == "music":
        _run_elevenlabs_music(step, ws, state)
    elif t == "fetch_assets":
        _run_fetch_assets(step, ws, state)
    elif t == "script":
        _run_script(step, ws, state)
    else:
        raise ValueError(f"Unknown step type: {t}")


def _execute_step(
    step: dict,
    ws: Path,
    state: dict,
    domain: str,
    run_id: str,
    force: bool = False,
    clean: bool = False,
) -> bool:
    sid = step["id"]

    if not force and _output_exists(step, ws):
        return True

    _mark_active(domain, run_id, sid)

    try:
        _dispatch(step, ws, state, clean)
        state["completed"] = list(dict.fromkeys([*state["completed"], sid]))
        state["failed"] = [x for x in state["failed"] if x != sid]
        save_state(ws, state)
        return True

    except Exception as exc:
        if sid not in state["failed"]:
            state["failed"].append(sid)
        save_state(ws, state)
        print(f"[tasks] Step {sid} failed: {exc}", flush=True)
        return False


# ─────────────────────────────────────────────────────────────
# Background thread targets
# ─────────────────────────────────────────────────────────────

def _run_full_pipeline(domain: str, run_id: str, ws: Path, state: dict) -> None:
    try:
        for step in STEPS:
            if not _execute_step(step, ws, state, domain, run_id):
                break
    finally:
        _mark_idle(domain, run_id)


def _run_preview(domain: str, run_id: str, ws: Path, state: dict) -> None:
    """Run only step 1 (Research) then stop — waits for user approval."""
    try:
        _execute_step(STEPS_BY_ID["1"], ws, state, domain, run_id, force=True)
    finally:
        _mark_idle(domain, run_id)


def _run_single_step(domain: str, run_id: str, ws: Path, state: dict, step: dict, force: bool) -> None:
    is_imagen = step["type"] == "imagen"
    is_animation_prompt = step["type"] == "animation_prompt"
    try:
        _execute_step(
            step, ws, state, domain, run_id,
            force=force or is_imagen,
            clean=force and (is_imagen or is_animation_prompt),
        )
    finally:
        _mark_idle(domain, run_id)


# ─────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────

class VideoConfig(BaseModel):
    duration_min_minutes: int
    duration_max_minutes: int
    video_split_percent: int


class StartRunRequest(BaseModel):
    domain: str
    fresh: bool = False
    preview_only: bool = False  # fresh-start preview: run step 1 only, then wait for approval
    video_config: Optional[VideoConfig] = None


class RunStepRequest(BaseModel):
    force: bool = False


class UpdateStepContentRequest(BaseModel):
    content: Optional[str] = None        # raw text steps (markdown/text)
    sections: Optional[list] = None      # research / story
    scenes: Optional[list] = None        # scene_plan
    asset_scenes: Optional[list] = None  # asset_manifest / asset_acquisition


class SaveAssetFilesRequest(BaseModel):
    files: list  # [{filename: str, content: str}]


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/estimate-cost")
def get_cost_estimate(duration_min: int = Query(...), duration_max: int = Query(...), video_split: int = Query(...)):
    return cost_estimate.estimate_cost_range(duration_min, duration_max, video_split)


@router.post("/runs")
def start_run(body: StartRunRequest):
    if body.domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{body.domain}'. Supported: {SUPPORTED_DOMAINS}")

    domain = body.domain

    if body.fresh:
        run_id, ws = new_workspace(domain)
        state = {
            "completed": [],
            "failed": [],
            "domain": domain,
            "voice_id": DOMAIN_VOICE_MAP[domain],
            "video_config": body.video_config.model_dump() if body.video_config else None,
        }
        save_state(ws, state)
    else:
        try:
            run_id, ws = latest_workspace(domain)
            state = load_state(ws)
        except RuntimeError:
            run_id, ws = new_workspace(domain)
            state = {
                "completed": [],
                "failed": [],
                "domain": domain,
                "voice_id": DOMAIN_VOICE_MAP[domain],
            }
            save_state(ws, state)

    is_preview = body.fresh and body.preview_only

    if not is_preview and not ENABLE_FULL_PIPELINE():
        return {
            "run_id": run_id,
            "domain": domain,
            "workspace": str(ws.relative_to(BASE_DIR)),
            "fresh": body.fresh,
            "preview_only": False,
            "message": "Workspace ready — run steps individually",
        }

    if _is_active(domain, run_id):
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is already active")

    _mark_active(domain, run_id, None)

    if is_preview:
        target = _run_preview
        message = "Preview started — awaiting approval after step 1"
    else:
        target = _run_full_pipeline
        message = "Full run started"

    thread = threading.Thread(
        target=target,
        args=(domain, run_id, ws, state),
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run_id,
        "domain": domain,
        "workspace": str(ws.relative_to(BASE_DIR)),
        "fresh": body.fresh,
        "preview_only": is_preview,
        "message": message,
    }


@router.post("/runs/{domain}/{run_id}/steps/{step_id}")
def run_step(domain: str, run_id: str, step_id: str, body: RunStepRequest):
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")

    step = STEPS_BY_ID.get(step_id)
    if step is None:
        raise HTTPException(status_code=400, detail=f"Unknown step '{step_id}'. Valid IDs: {list(STEPS_BY_ID)}")

    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if _is_active(domain, run_id):
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is already active")

    state = load_state(ws)
    _mark_active(domain, run_id, step_id)

    thread = threading.Thread(
        target=_run_single_step,
        args=(domain, run_id, ws, state, step, body.force),
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run_id,
        "domain": domain,
        "step_id": step_id,
        "force": body.force,
        "message": "Step queued",
    }


@router.get("/runs/{domain}/{run_id}")
def get_run_status(domain: str, run_id: str):
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")

    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    state = load_state(ws)
    active_info = _get_active(domain, run_id)
    active_step_id = active_info["step_id"] if active_info else None

    steps_out = []
    for step in STEPS:
        sid = step["id"]
        if sid == active_step_id:
            status = "running"
        elif sid in state.get("completed", []) or _output_exists(step, ws):
            status = "done"
        elif sid in state.get("failed", []):
            status = "failed"
        else:
            status = "pending"
        steps_out.append({"id": sid, "name": step["name"], "type": step["type"], "status": status})

    return {
        "run_id": run_id,
        "domain": domain,
        "voice_id": state.get("voice_id"),
        "workspace": str(ws.relative_to(BASE_DIR)),
        "active": active_info is not None,
        "active_step": active_step_id,
        "steps": steps_out,
    }


@router.delete("/runs/{domain}/{run_id}")
def delete_run(domain: str, run_id: str):
    """Delete a workspace — used to discard a rejected preview run."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")

    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if _is_active(domain, run_id):
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is still active — stop it first")

    import shutil
    shutil.rmtree(ws)
    return {"run_id": run_id, "domain": domain, "message": "Run deleted"}


@router.post("/runs/{domain}/{run_id}/continue")
def continue_run(domain: str, run_id: str):
    """Resume the full pipeline after preview approval — runs all remaining steps."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    if not ENABLE_FULL_PIPELINE():
        raise HTTPException(status_code=409, detail="Full pipeline run is disabled")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if _is_active(domain, run_id):
        raise HTTPException(status_code=409, detail=f"Run '{run_id}' is already active")

    state = load_state(ws)
    _mark_active(domain, run_id, None)

    thread = threading.Thread(
        target=_run_full_pipeline,
        args=(domain, run_id, ws, state),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "domain": domain, "message": "Pipeline resumed"}


@router.get("/runs")
def list_runs(domain: Optional[str] = Query(default=None)):
    if domain is not None and domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")

    result = []

    domains_to_scan = [domain] if domain else SUPPORTED_DOMAINS

    for d in domains_to_scan:
        domain_dir = WORKSPACE_ROOT / d
        if not domain_dir.exists():
            continue

        for ws_dir in sorted(domain_dir.iterdir(), reverse=True):
            if not ws_dir.is_dir() or not re.match(r"\d{4}-\d{2}-\d{2}_\d{6}", ws_dir.name):
                continue

            run_id = ws_dir.name
            state = load_state(ws_dir)

            # Parse created_at from folder name
            try:
                created_at = datetime.strptime(run_id, "%Y-%m-%d_%H%M%S").isoformat()
            except ValueError:
                created_at = None

            # Collect animated.mp4 files
            assets_dir = ws_dir / "assets"
            videos = []
            if assets_dir.exists():
                videos = [
                    str(p.relative_to(BASE_DIR))
                    for p in sorted(assets_dir.rglob("animated.mp4"))
                ]

            active_info = _get_active(d, run_id)

            result.append({
                "domain": d,
                "run_id": run_id,
                "workspace": str(ws_dir.relative_to(BASE_DIR)),
                "created_at": created_at,
                "active": active_info is not None,
                "active_step": active_info["step_id"] if active_info else None,
                "steps_completed": len(state.get("completed", [])),
                "steps_failed": len(state.get("failed", [])),
                "steps_total": len(STEPS),
                "videos": videos,
            })

    return result


# ─────────────────────────────────────────────────────────────
# Step content config
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Document parsers / serializers
# ─────────────────────────────────────────────────────────────

def _strip_label_bold(line: str) -> str:
    """Strip a markdown bold wrapper around a leading label, e.g. '**LABEL:**
    value' -> 'LABEL: value' or '**LABEL**' -> 'LABEL'. LLM output formatting
    varies across models/providers (OpenRouter vs. native Gemini) — some wrap
    section/field labels in bold, some don't — so parsers normalize this away
    rather than relying on exact prompt compliance."""
    return re.sub(r'^\*\*(.+?)\*\*', r'\1', line, count=1)


def _is_section_header(line: str) -> bool:
    t = _strip_label_bold(line.strip())
    if not t or t.startswith('*') or t.startswith('-') or t.startswith('#') or re.match(r'^\d+\.', t):
        return False
    if re.match(r'^[A-Z][A-Z\s\(\)\/\-\.,0-9]+$', t) and len(t) < 70:
        return True
    if re.match(r'^[A-Z][a-z\-\s]+$', t) and len(t) < 40:
        return True
    return False


def _parse_sections(text: str) -> list:
    """Parse a flat ALL-CAPS section document into [{label, content}]."""
    sections = []
    current_label: Optional[str] = None
    current_lines: list = []

    def flush():
        if current_label is not None:
            sections.append({"label": current_label, "content": "\n".join(current_lines).strip()})

    for line in text.splitlines():
        if _is_section_header(line):
            flush()
            current_label = _strip_label_bold(line.strip())
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return sections


def _serialize_sections(sections: list) -> str:
    return "\n\n".join(f"{s['label']}\n\n{s['content'].strip()}" for s in sections)


def _split_visual_purpose(value: str) -> tuple:
    """Split 'VISUAL: X. To Y.' into (visual, purpose)."""
    t = value.strip()
    if not t.upper().startswith("VISUAL:"):
        return ("", t)
    rest = re.sub(r'^VISUAL:\s*', '', t, flags=re.IGNORECASE)
    m = re.search(r'\.\s+To\s+', rest, re.IGNORECASE)
    if m:
        return (rest[:m.start()].strip(), rest[m.end():].rstrip('.').strip())
    return (rest, "")


def _parse_beats(scene_text: str) -> list:
    beats: list = []
    current: dict = {}
    current_key: Optional[str] = None
    current_value_lines: list = []

    def flush_key():
        nonlocal current_key, current_value_lines
        if current_key is not None:
            value = "\n".join(current_value_lines).strip()
            if current_key == "purpose":
                visual, purpose = _split_visual_purpose(value)
                current["visual"] = visual
                current["purpose"] = purpose
            else:
                current[current_key] = value
        current_key = None
        current_value_lines = []

    def flush_beat():
        flush_key()
        if current.get("narration"):
            beats.append(dict(current))
        current.clear()

    for line in scene_text.splitlines():
        t = _strip_label_bold(line.strip())
        m = re.match(r'^(Narration|Duration|Purpose|Emotion|Animate):\s*(.*)$', t, re.IGNORECASE)
        if m:
            key = m.group(1).lower()
            inline = m.group(2).strip()
            if key == "narration" and current.get("narration"):
                flush_beat()
            flush_key()
            current_key = key
            current_value_lines = [inline] if inline else []
        elif current_key:
            current_value_lines.append(line)

    flush_beat()
    return beats


def _parse_scene_plan(text: str) -> list:
    scenes: list = []
    current_id: Optional[int] = None
    current_lines: list = []

    def flush_scene():
        nonlocal current_id, current_lines
        if current_id is not None:
            scenes.append({"id": current_id, "beats": _parse_beats("\n".join(current_lines))})
        current_id = None
        current_lines = []

    for line in text.splitlines():
        t = line.strip()
        m = re.match(r'^SCENE\s+(\d+)$', t)
        if m:
            flush_scene()
            current_id = int(m.group(1))
        elif t == '---':
            pass
        elif current_id is not None:
            current_lines.append(line)

    flush_scene()
    return scenes


def _serialize_scene_plan(scenes: list) -> str:
    parts = []
    for scene in scenes:
        lines = [f"SCENE {scene['id']}", ""]
        for beat in scene.get("beats", []):
            visual = beat.get("visual", "")
            purpose = beat.get("purpose", "")
            if visual and purpose:
                purpose_field = f"VISUAL: {visual}. To {purpose}."
            elif visual:
                purpose_field = f"VISUAL: {visual}."
            else:
                purpose_field = purpose
            lines += [
                "Narration:", beat.get("narration", ""),
                "Duration:",  beat.get("duration", ""),
                "Purpose:",   purpose_field,
                "Emotion:",   beat.get("emotion", ""),
                "Animate:",   beat.get("animate", ""),
                "",
            ]
        parts.append("\n".join(lines))
    return "\n---\n\n".join(parts)


def _parse_asset_manifest_scenes(text: str) -> list:
    """Parse asset_manifest.md into scenes.

    Supports both the markdown-heading format with explicit N.M asset
    sub-ids (produced when a manifest is edited/saved via the UI) and the
    plain "SCENE N" / KEY: value format the asset-planning prompt actually
    asks the model to produce, where each scene has a single implicit asset.
    """
    scenes: list = []
    current_fields: list = []
    current_asset_id: Optional[str] = None
    current_field_label: Optional[str] = None
    current_field_lines: list = []

    def flush_field():
        nonlocal current_field_label, current_field_lines
        if current_field_label is not None:
            current_fields.append({"label": current_field_label, "content": "\n".join(current_field_lines).strip()})
        current_field_label = None
        current_field_lines = []

    def flush_asset():
        flush_field()
        if current_asset_id is not None and scenes:
            scenes[-1]["assets"].append({"id": current_asset_id, "fields": list(current_fields)})
            current_fields.clear()

    for line in text.splitlines():
        t = _strip_label_bold(line.strip())

        # Scene: ### SCENE N, # SCENE N, or plain SCENE N
        m = re.match(r'^#{0,4}\s*SCENE\s+(\d+)\b', t, re.IGNORECASE)
        if m:
            flush_asset()
            current_asset_id = None
            scenes.append({"id": int(m.group(1)), "assets": []})
            continue

        # Asset: **N.M** (bold in markdown)
        m = re.match(r'^\*{0,2}(\d+\.\d+)\*{0,2}$', t)
        if m and scenes:
            flush_asset()
            current_asset_id = m.group(1)
            current_fields.clear()
            continue

        # Skip separators and empty lines when not in an asset
        if t in ('---', '***', '* * *') or (not t and current_asset_id is None):
            continue

        if scenes:
            # Field with inline value: KEY: value
            m = re.match(r'^([A-Z][A-Z_]+):\s*(.*)$', t)
            if m:
                if current_asset_id is None:
                    # No explicit N.M sub-id under this scene — treat it as one implicit asset.
                    current_asset_id = "1"
                flush_field()
                current_field_label = m.group(1)
                inline = m.group(2).strip()
                current_field_lines = [inline] if inline else []
            elif current_asset_id is not None and current_field_label is not None:
                # Multi-line continuation (e.g. STOCK_QUERIES list)
                current_field_lines.append(line.rstrip())

    flush_asset()
    return scenes


def _serialize_asset_manifest(scenes: list) -> str:
    parts = ["Here is the visual asset breakdown for your documentary.", "", "***"]
    for scene in scenes:
        parts += ["", f"### SCENE {scene['id']}", ""]
        for asset in scene.get("assets", []):
            parts.append(f"**{asset['id']}**")
            for field in asset.get("fields", []):
                label = field["label"]
                value = field["content"]
                if "\n" in value:
                    parts.append(f"{label}:")
                    parts.extend(value.split("\n"))
                else:
                    parts.append(f"{label}: {value}")
            parts.append("")
        parts.append("---")
    return "\n".join(parts)


def _parse_asset_acquisition(text: str) -> list:
    """Parse asset_acquisition.md (SCENE N / ASSET N.M / LABEL:\\nvalue) into scenes."""
    scenes: list = []
    current_scene_id: Optional[int] = None
    current_asset_id: Optional[str] = None
    current_fields: list = []
    current_field_label: Optional[str] = None
    current_field_lines: list = []

    def flush_field():
        nonlocal current_field_label, current_field_lines
        if current_field_label is not None:
            current_fields.append({"label": current_field_label, "content": "\n".join(current_field_lines).strip()})
        current_field_label = None
        current_field_lines = []

    def flush_asset():
        flush_field()
        if current_asset_id is not None:
            scene = next((s for s in scenes if s["id"] == current_scene_id), None)
            if scene is not None:
                scene["assets"].append({"id": current_asset_id, "fields": list(current_fields)})
            current_fields.clear()

    for line in text.splitlines():
        t = _strip_label_bold(line.strip())
        if not t or t in ('---', '***'):
            continue

        # Scene: SCENE N
        m = re.match(r'^SCENE\s+(\d+)$', t)
        if m:
            sid = int(m.group(1))
            if sid != current_scene_id:
                flush_asset()
                current_scene_id = sid
                current_asset_id = None
                if not any(s["id"] == sid for s in scenes):
                    scenes.append({"id": sid, "assets": []})
            continue

        # Asset: ASSET N.M, or plain ASSET N (model doesn't always use the
        # dotted scene.asset sub-id convention)
        m = re.match(r'^ASSET\s+(\d+(?:\.\d+)?)$', t)
        if m and current_scene_id is not None:
            flush_asset()
            current_asset_id = m.group(1)
            current_fields.clear()
            continue

        if current_asset_id is not None:
            # Field label only: LABEL:
            m = re.match(r'^([A-Z][A-Z_]+):$', t)
            if m:
                flush_field()
                current_field_label = m.group(1)
                current_field_lines = []
                continue
            # Inline field: LABEL: value
            m = re.match(r'^([A-Z][A-Z_]+):\s+(.+)$', t)
            if m and not re.match(r'^\d+\.', t):
                flush_field()
                current_field_label = m.group(1)
                current_field_lines = [m.group(2).strip()]
                continue
            # Value continuation
            if current_field_label is not None:
                current_field_lines.append(line.rstrip())

    flush_asset()
    return scenes


def _serialize_asset_acquisition(scenes: list) -> str:
    parts = []
    for scene in scenes:
        for asset in scene.get("assets", []):
            parts.append(f"SCENE {scene['id']}")
            parts.append(f"ASSET {asset['id']}")
            for field in asset.get("fields", []):
                parts.append(f"{field['label']}:")
                parts.append(field["content"])
            parts.append("")
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────

STEP_CONTENT_CONFIG: dict = {
    "1":  {"kind": "research",    "file": "research_dossier.md"},
    "2":  {"kind": "story",       "file": "story_script.md"},
    "3":  {"kind": "scene_plan",       "file": "scene_plan.md"},
    "4":  {"kind": "asset_manifest",   "file": "asset_manifest.md"},
    "5":  {"kind": "asset_acquisition","file": "asset_acquisition.md"},
    "6":  {"kind": "assets_viewer"},
    "7":  {"kind": "image_list"},
    "8":  {"kind": "animation_list"},
    "9":  {"kind": "video_list"},
    "10": {"kind": "markdown", "file": "narration_script.txt"},
    "11": {"kind": "audio",    "file": "narration.mp3"},
    "12": {"kind": "text",     "file": "music_prompt.txt"},
    "13": {"kind": "audio",    "file": "music.wav"},
    "14": {"kind": "text",     "file": "asset_inventory.txt"},
    "15": {"kind": "json",     "file": "narration_timing.json"},
    "16": {"kind": "json",     "file": "edl.json"},
    "17": {"kind": "video",    "file": "output/final_video.mp4"},
    "18": {"kind": "json",     "file": "platform_metadata.json"},
}


@router.get("/runs/{domain}/{run_id}/steps/{step_id}/content")
def get_step_content(domain: str, run_id: str, step_id: str):
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    if STEPS_BY_ID.get(step_id) is None:
        raise HTTPException(status_code=400, detail=f"Unknown step '{step_id}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    cfg = STEP_CONTENT_CONFIG.get(step_id)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"No content config for step {step_id}")

    kind = cfg["kind"]

    if kind in ("research", "story"):
        fp = ws / cfg["file"]
        if not fp.exists():
            return {"kind": kind, "sections": []}
        return {"kind": kind, "sections": _parse_sections(fp.read_text())}

    if kind == "scene_plan":
        fp = ws / cfg["file"]
        if not fp.exists():
            return {"kind": kind, "scenes": []}
        return {"kind": kind, "scenes": _parse_scene_plan(fp.read_text())}

    if kind == "asset_manifest":
        fp = ws / cfg["file"]
        if not fp.exists():
            return {"kind": kind, "scenes": []}
        return {"kind": kind, "scenes": _parse_asset_manifest_scenes(fp.read_text())}

    if kind == "asset_acquisition":
        fp = ws / cfg["file"]
        if not fp.exists():
            return {"kind": kind, "scenes": []}
        return {"kind": kind, "scenes": _parse_asset_acquisition(fp.read_text())}

    if kind in ("markdown", "text"):
        fp = ws / cfg["file"]
        return {"kind": kind, "content": fp.read_text() if fp.exists() else None}

    if kind == "json":
        raw = cfg["file"]
        fp = (BASE_DIR / raw) if raw.startswith("output/") else (ws / raw)
        if not fp.exists():
            return {"kind": kind, "content": None}
        try:
            return {"kind": kind, "content": json.loads(fp.read_text())}
        except json.JSONDecodeError:
            return {"kind": "text", "content": fp.read_text()}

    if kind == "audio":
        fp = ws / cfg["file"]
        url = f"/tasks/files/{domain}/{run_id}/{cfg['file']}" if fp.exists() else None
        return {"kind": kind, "url": url}

    if kind == "video":
        raw = cfg["file"]
        fp = (BASE_DIR / raw) if raw.startswith("output/") else (ws / raw)
        url = f"/tasks/files/{domain}/{run_id}/{raw}" if fp.exists() else None
        return {"kind": kind, "url": url}

    if kind == "image_list":
        assets_dir = ws / "assets"
        images = []
        seen_dirs: set = set()
        if assets_dir.exists():
            for pat in ("image.png", "image.jpg"):
                for f in sorted(assets_dir.rglob(pat)):
                    if f.parent in seen_dirs:
                        continue
                    seen_dirs.add(f.parent)
                    rel = str(f.relative_to(ws))
                    parts = f.parent.parts
                    scene_id = asset_id = ""
                    for p in parts:
                        if p.startswith("scene_"):
                            scene_id = p[len("scene_"):]
                        elif p.startswith("asset_"):
                            asset_id = p[len("asset_"):]
                    images.append({
                        "path": rel,
                        "url": f"/tasks/files/{domain}/{run_id}/{rel}",
                        "label": str(f.parent.relative_to(assets_dir)),
                        "scene_id": scene_id,
                        "asset_id": asset_id,
                        "filename": f.name,
                    })
        return {"kind": kind, "images": images}

    if kind == "animation_list":
        assets_dir = ws / "assets"
        items = []
        if assets_dir.exists():
            for f in sorted(assets_dir.rglob("animated.txt")):
                rel = str(f.relative_to(ws))
                parts = f.parent.parts
                scene_id = asset_id = ""
                for p in parts:
                    if p.startswith("scene_"):
                        scene_id = p[len("scene_"):]
                    elif p.startswith("asset_"):
                        asset_id = p[len("asset_"):]

                image_url = None
                for candidate in ("image.png", "image.jpg", "map.png", "chart.png"):
                    ip = f.parent / candidate
                    if ip.exists():
                        image_url = f"/tasks/files/{domain}/{run_id}/{ip.relative_to(ws)}"
                        break

                items.append({
                    "path": rel,
                    "text": f.read_text().strip(),
                    "label": str(f.parent.relative_to(assets_dir)),
                    "scene_id": scene_id,
                    "asset_id": asset_id,
                    "image_url": image_url,
                })
        return {"kind": kind, "items": items}

    if kind == "video_list":
        assets_dir = ws / "assets"
        videos = []
        if assets_dir.exists():
            for txt_file in sorted(assets_dir.rglob("animated.txt")):
                asset_dir = txt_file.parent
                parts = asset_dir.parts
                scene_id = asset_id = ""
                for p in parts:
                    if p.startswith("scene_"):
                        scene_id = p[len("scene_"):]
                    elif p.startswith("asset_"):
                        asset_id = p[len("asset_"):]

                thumbnail_url = None
                for candidate in ("image.png", "image.jpg", "map.png", "chart.png"):
                    cp = asset_dir / candidate
                    if cp.exists():
                        rel = str(cp.relative_to(ws))
                        thumbnail_url = f"/tasks/files/{domain}/{run_id}/{rel}"
                        break

                mp4 = asset_dir / "animated.mp4"
                video_url = None
                if mp4.exists():
                    rel = str(mp4.relative_to(ws))
                    video_url = f"/tasks/files/{domain}/{run_id}/{rel}"

                videos.append({
                    "scene_id": scene_id,
                    "asset_id": asset_id,
                    "label": str(asset_dir.relative_to(assets_dir)),
                    "thumbnail_url": thumbnail_url,
                    "prompt": txt_file.read_text().strip(),
                    "video_url": video_url,
                    "status": "done" if video_url else "pending",
                })
        return {"kind": kind, "videos": videos}

    if kind == "assets_viewer":
        assets_dir = ws / "assets"
        # Ordered file label map — image first, then text files
        FILE_LABELS = {
            "image.png":       ("image", "Image"),
            "image.jpg":       ("image", "Image"),
            "generated.txt":   ("text",  "AI Prompt"),
            "search_query.txt":("text",  "Search Query"),
            "animated.txt":    ("text",  "Animation Prompt"),
            "map_spec.json":   ("text",  "Map Spec"),
            "chart_spec.json": ("text",  "Chart Spec"),
        }
        scenes_out = []
        if assets_dir.exists():
            for scene_dir in sorted(assets_dir.iterdir()):
                if not scene_dir.is_dir() or not scene_dir.name.startswith("scene_"):
                    continue
                scene_id = scene_dir.name[len("scene_"):]
                assets_out = []
                for asset_dir in sorted(scene_dir.iterdir()):
                    if not asset_dir.is_dir() or not asset_dir.name.startswith("asset_"):
                        continue
                    asset_id = asset_dir.name[len("asset_"):]
                    files_out = []
                    for fname, (ftype, label) in FILE_LABELS.items():
                        fp2 = asset_dir / fname
                        if not fp2.exists():
                            continue
                        if ftype == "image":
                            rel = str(fp2.relative_to(ws))
                            files_out.append({"type": "image", "label": label, "filename": fname, "url": f"/tasks/files/{domain}/{run_id}/{rel}"})
                        else:
                            files_out.append({"type": "text", "label": label, "filename": fname, "content": fp2.read_text()})
                    if files_out:
                        assets_out.append({"id": asset_id, "files": files_out})
                if assets_out:
                    scenes_out.append({"id": scene_id, "assets": assets_out})
        return {"kind": kind, "scenes": scenes_out}

    raise HTTPException(status_code=500, detail=f"Unknown content kind: {kind}")


@router.put("/runs/{domain}/{run_id}/steps/{step_id}/content")
def update_step_content(domain: str, run_id: str, step_id: str, body: UpdateStepContentRequest):
    """Overwrite a step's output file with edited content."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    if STEPS_BY_ID.get(step_id) is None:
        raise HTTPException(status_code=400, detail=f"Unknown step '{step_id}'")

    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    cfg = STEP_CONTENT_CONFIG.get(step_id)
    if not cfg or cfg["kind"] not in ("markdown", "text", "research", "story", "scene_plan", "asset_manifest", "asset_acquisition"):
        raise HTTPException(status_code=400, detail=f"Step {step_id} content is not editable")

    fp = ws / cfg["file"]
    fp.parent.mkdir(parents=True, exist_ok=True)

    if body.sections is not None:
        fp.write_text(_serialize_sections(body.sections))
    elif body.scenes is not None:
        fp.write_text(_serialize_scene_plan(body.scenes))
    elif body.asset_scenes is not None:
        if cfg["kind"] == "asset_manifest":
            fp.write_text(_serialize_asset_manifest(body.asset_scenes))
        else:
            fp.write_text(_serialize_asset_acquisition(body.asset_scenes))
    elif body.content is not None:
        fp.write_text(body.content)
    else:
        raise HTTPException(status_code=400, detail="No content provided")

    return {"run_id": run_id, "step_id": step_id, "message": "Content updated"}


@router.put("/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}")
def save_asset_files(domain: str, run_id: str, scene_id: str, asset_id: str, body: SaveAssetFilesRequest):
    """Save edited text files for a single asset."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    asset_dir = ws / "assets" / f"scene_{scene_id}" / f"asset_{asset_id}"
    if not asset_dir.exists():
        raise HTTPException(status_code=404, detail=f"Asset directory not found: {asset_dir.name}")

    ALLOWED_TEXT_FILES = {"generated.txt", "search_query.txt", "animated.txt", "map_spec.json", "chart_spec.json"}
    for item in body.files:
        fname = item["filename"]
        if fname not in ALLOWED_TEXT_FILES:
            raise HTTPException(status_code=400, detail=f"File not editable: {fname}")
        (asset_dir / fname).write_text(item["content"])

    return {"message": "Asset files saved"}


@router.post("/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/image")
async def upload_asset_image(domain: str, run_id: str, scene_id: str, asset_id: str, file: UploadFile = File(...)):
    """Upload a replacement image for an asset."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    asset_dir = ws / "assets" / f"scene_{scene_id}" / f"asset_{asset_id}"
    if not asset_dir.exists():
        raise HTTPException(status_code=404, detail=f"Asset directory not found")

    # Always save as image.png regardless of upload format
    dest = asset_dir / "image.png"
    content = await file.read()
    dest.write_bytes(content)

    rel = str(dest.relative_to(ws))
    return {
        "message": "Image uploaded",
        "url": f"/tasks/files/{domain}/{run_id}/{rel}",
    }


@router.post("/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/regenerate-image")
def regenerate_asset_image(domain: str, run_id: str, scene_id: str, asset_id: str):
    """Delete the current image for an asset and regenerate it (Imagen or web-fetch)."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    asset_dir = ws / "assets" / f"scene_{scene_id}" / f"asset_{asset_id}"
    if not asset_dir.exists():
        raise HTTPException(status_code=404, detail="Asset directory not found")

    # Clear existing image and block marker
    for fname in ("image.png", "image.jpg", "blocked.txt"):
        p = asset_dir / fname
        if p.exists():
            p.unlink()

    if MOCK_AI():
        from mocks.generators import generate_placeholder_image
        out = asset_dir / "image.png"
        generate_placeholder_image(out)
        rel = str(out.relative_to(ws))
        return {"url": f"/tasks/files/{domain}/{run_id}/{rel}"}

    generated_txt   = asset_dir / "generated.txt"
    search_query_txt = asset_dir / "search_query.txt"

    if generated_txt.exists() and USE_OPENROUTER():
        from open_router.image import generate_image
        image_prompt = generated_txt.read_text().strip()
        out = asset_dir / "image.png"
        blocked_marker = asset_dir / "blocked.txt"
        try:
            out.write_bytes(generate_image(image_prompt, api_key=OPENROUTER_API_KEY()))
        except Exception as e:
            blocked_marker.write_text(str(e))
            raise HTTPException(status_code=422, detail=f"Image generation failed: {e}")
        rel = str(out.relative_to(ws))
        return {"url": f"/tasks/files/{domain}/{run_id}/{rel}"}

    if generated_txt.exists():
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise HTTPException(status_code=500, detail="Missing dependency: google-genai")

        client = genai.Client(api_key=GEMINI_API_KEY())
        image_prompt = generated_txt.read_text().strip()
        out = asset_dir / "image.png"
        blocked_marker = asset_dir / "blocked.txt"
        try:
            response = client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=image_prompt,
                config=types.GenerateImagesConfig(number_of_images=1),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        if response.generated_images:
            out.write_bytes(response.generated_images[0].image.image_bytes)
            rel = str(out.relative_to(ws))
            return {"url": f"/tasks/files/{domain}/{run_id}/{rel}"}
        reason = getattr(response, "rai_filtered_reason", None) or "safety filter"
        blocked_marker.write_text(reason)
        raise HTTPException(status_code=422, detail=f"Image blocked by safety filter: {reason}")

    if search_query_txt.exists():
        query = search_query_txt.read_text().strip()
        ok = _fetch_real_image(query, asset_dir)
        if ok:
            for fname in ("image.jpg", "image.png"):
                p = asset_dir / fname
                if p.exists():
                    rel = str(p.relative_to(ws))
                    return {"url": f"/tasks/files/{domain}/{run_id}/{rel}"}
        raise HTTPException(status_code=404, detail="No image found from web search")

    raise HTTPException(status_code=400, detail="No image source (generated.txt or search_query.txt) found for this asset")


@router.post("/runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/animate")
def animate_asset(domain: str, run_id: str, scene_id: str, asset_id: str):
    """Delete the current animated.mp4 for an asset (if any) and animate it."""
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    asset_dir = ws / "assets" / f"scene_{scene_id}" / f"asset_{asset_id}"
    if not asset_dir.exists():
        raise HTTPException(status_code=404, detail="Asset directory not found")

    txt_file = asset_dir / "animated.txt"
    if not txt_file.exists():
        raise HTTPException(status_code=400, detail="No animation prompt (animated.txt) found for this asset")

    out_mp4 = asset_dir / "animated.mp4"
    if out_mp4.exists():
        out_mp4.unlink()

    try:
        _animate_single_asset(txt_file)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Animation failed: {e}")

    rel = str(out_mp4.relative_to(ws))
    return {"url": f"/tasks/files/{domain}/{run_id}/{rel}"}


@router.get("/files/{domain}/{run_id}/{file_path:path}")
def serve_file(domain: str, run_id: str, file_path: str):
    if domain not in SUPPORTED_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    try:
        ws = find_workspace(domain, run_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    full = (BASE_DIR / file_path) if file_path.startswith("output/") else (ws / file_path)

    if not full.exists() or not full.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Security: path must be inside workspace or project output dir
    try:
        full.relative_to(ws)
    except ValueError:
        try:
            full.relative_to(BASE_DIR / "output")
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

    mime, _ = mimetypes.guess_type(str(full))
    return FileResponse(path=str(full), media_type=mime or "application/octet-stream")


# ─────────────────────────────────────────────────────────────
# Standalone app
# ─────────────────────────────────────────────────────────────

import settings as _settings

app = FastAPI(title="VidLife Tasks API")
app.include_router(router)
app.include_router(_settings.router, prefix="/tasks")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
