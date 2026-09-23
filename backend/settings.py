"""
backend/settings.py — API key / service config management.

Reads and writes settings.json at the project root.
Mounted at /tasks in the standalone app (tasks.py).
"""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

BASE_DIR      = Path(__file__).parent.parent
SETTINGS_FILE = BASE_DIR / "settings.json"

SETTINGS_KEYS = [
    {"key": "GEMINI_API_KEY",     "label": "Gemini API Key",     "secret": True},
    {"key": "ELEVENLABS_API_KEY", "label": "ElevenLabs API Key", "secret": True},
    {"key": "PEXELS_API_KEY",     "label": "Pexels API Key",     "secret": True},
    {"key": "PIXABAY_API_KEY",    "label": "Pixabay API Key",    "secret": True},
    {"key": "RUNPOD_URL",         "label": "RunPod URL",         "secret": False},
    {"key": "OPENROUTER_API_KEY", "label": "OpenRouter API Key", "secret": True},
    {"key": "USE_OPENROUTER",     "label": "Use OpenRouter (alternative AI provider)", "secret": False, "type": "bool"},
    {"key": "MOCK_AI",            "label": "Mock AI (dev mode)", "secret": False, "type": "bool"},
]


def load() -> dict:
    """Return current settings, preferring settings.json over env vars."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {s["key"]: os.environ.get(s["key"], "") for s in SETTINGS_KEYS}


def save(data: dict) -> None:
    """Persist settings and apply them to the current process."""
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))
    for k, v in data.items():
        if v and isinstance(v, str):
            os.environ[k] = v


# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(tags=["settings"])


class UpdateSettingsRequest(BaseModel):
    settings: dict[str, Any]


@router.get("/settings")
def get_settings():
    return {"fields": SETTINGS_KEYS, "values": load()}


@router.put("/settings")
def update_settings(body: UpdateSettingsRequest):
    allowed = {s["key"] for s in SETTINGS_KEYS}
    current = load()
    current.update({k: v for k, v in body.settings.items() if k in allowed})
    save(current)
    return {"message": "Settings saved"}
