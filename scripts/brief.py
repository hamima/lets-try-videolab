#!/usr/bin/env python3
"""
Step 0: Brief intake — ask once, then lock the creative constraints for the whole run.

Prompts for (with sensible defaults):
  * length target (seconds)
  * audience
  * title / end-card style
  * fit mode (contain | fill)
  * music mood
  * show section titles (yes/no)

Writes: composition/brief.json  (single source of truth consumed by tts.py,
compose.py, soundtrack.py, render.py, checks.py)

Usage:
    python scripts/brief.py          # interactive (press Enter to accept defaults)
    python scripts/brief.py --show   # print current brief.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = BASE_DIR / "composition"
BRIEF_PATH = COMPOSITION_DIR / "brief.json"

DEFAULTS = {
    "length_target_seconds": 90,          # 60-120s documentary
    "audience": "general adult",
    "title_end_card_style": "clean minimal (white text on dark)",
    "fit_mode": "contain",                # contain | fill
    "music_mood": "ambient / neutral",
    "show_section_titles": True,
    "voice_sample_voices": ["af_heart", "af_bella", "bf_emma", "am_michael"],
    "wpm_min": 140,
    "wpm_max": 165,
}


def _ask(prompt: str, default) -> str:
    """Ask one question; return the user's answer or the default."""
    disp = default
    if isinstance(default, bool):
        disp = "yes" if default else "no"
    ans = input(f"{prompt} [{disp}]: ").strip()
    if not ans:
        return str(default)
    return ans


def _ask_bool(prompt: str, default: bool) -> bool:
    ans = _ask(prompt, default).lower()
    if ans in ("y", "yes", "true", "1"):
        return True
    if ans in ("n", "no", "false", "0"):
        return False
    return default


def run(force: bool = False) -> dict:
    if not force and BRIEF_PATH.exists():
        print(f"✓ Brief already exists at {BRIEF_PATH} — loading (use --force to re-ask)")
        return load()

    print("=" * 60)
    print("VIDEO BRIEF — answer once (Enter = accept default)")
    print("=" * 60)

    brief: dict = {}
    brief["length_target_seconds"] = int(
        _ask("Length target (seconds)", DEFAULTS["length_target_seconds"])
    )
    brief["audience"] = _ask("Audience", DEFAULTS["audience"])
    brief["title_end_card_style"] = _ask(
        "Title / end-card style", DEFAULTS["title_end_card_style"]
    )
    fit = _ask("Fit mode (contain/fill)", DEFAULTS["fit_mode"]).lower()
    if fit not in ("contain", "fill"):
        fit = DEFAULTS["fit_mode"]
    brief["fit_mode"] = fit
    brief["music_mood"] = _ask("Music mood", DEFAULTS["music_mood"])
    brief["show_section_titles"] = _ask_bool(
        "Show section titles?", DEFAULTS["show_section_titles"]
    )
    brief["voice_sample_voices"] = DEFAULTS["voice_sample_voices"]
    brief["wpm_min"] = DEFAULTS["wpm_min"]
    brief["wpm_max"] = DEFAULTS["wpm_max"]

    COMPOSITION_DIR.mkdir(parents=True, exist_ok=True)
    BRIEF_PATH.write_text(json.dumps(brief, indent=2))
    print(f"\n✓ Brief saved to {BRIEF_PATH}")
    print(json.dumps(brief, indent=2))
    return brief


def load() -> dict:
    if not BRIEF_PATH.exists():
        raise FileNotFoundError(
            f"{BRIEF_PATH} not found — run `python scripts/brief.py` first"
        )
    return json.loads(BRIEF_PATH.read_text())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--show", action="store_true", help="print current brief and exit")
    args = p.parse_args()
    if args.show:
        print(json.dumps(load(), indent=2))
    else:
        run()
