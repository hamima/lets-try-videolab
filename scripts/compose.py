#!/usr/bin/env python3
"""
Step 2: Compose — build composition/index.html (+ per-scene scene_N.html).

Reads:
  composition/audio/timings.json        (per-scene word start/end — MASTER CLOCK)
  composition/assets/manifest.json      (authored: images, cues, text, cards per scene)
  composition/brief.json                (fit_mode, show_section_titles, ...)
  composition/template.html + driver.js

Writes:
  composition/index.html                (composition entry)
  composition/scene_NN.html             (one self-contained 1920x1080 scene each)
  composition/render_order.json         (ordered scene durations for render.py)

Cue validation:
  Fail the build if a cue names a word the narration does not say.

Usage:
    python scripts/compose.py
"""
from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = BASE_DIR / "composition"
AUDIO_DIR = COMPOSITION_DIR / "audio"
ASSETS_DIR = COMPOSITION_DIR / "assets"
TEMPLATE_PATH = COMPOSITION_DIR / "template.html"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"
BRIEF_PATH = COMPOSITION_DIR / "brief.json"
TIMINGS_PATH = AUDIO_DIR / "timings.json"

DEFAULT_MANIFEST = {
    "scenes": [
        {
            "scene": 1,
            "title": "Section One",
            "backdrop": None,
            "fit_mode": "contain",
            "assets": [],
            "text": [],
            "lowerThird": {"kicker": "SECTION 1", "title": "Section One", "show_seconds": 2},
            "titleCard": None,
            "endCard": None,
        }
    ]
}


def _load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def timings_scene_words(timings, scene_no):
    for s in timings.get("scenes", []):
        if s["scene"] == scene_no:
            return [w["word"].lower().strip(".,!?:;\"'") for w in s.get("words", [])]
    return []


def _scene_start(timings, scene_no):
    for s in timings.get("scenes", []):
        if s["scene"] == scene_no:
            return round(s["start_sec"], 4)
    return 0.0


def _scene_duration(timings, scene_no):
    for s in timings.get("scenes", []):
        if s["scene"] == scene_no:
            return round(s["end_sec"] - s["start_sec"], 4)
    return 10.0


def _validate_cues(scenes, timings):
    """Fail the build if any cue_word is not spoken in its scene's narration."""
    errors = []
    for scene in scenes:
        scene_no = scene["scene"]
        spoken = set(timings_scene_words(timings, scene_no))
        for asset in scene.get("assets", []):
            cue = (asset.get("cue_word") or "").strip()
            if not cue:
                continue
            cue_norm = cue.lower().strip(".,!?:;\"'")
            if cue_norm and cue_norm not in spoken:
                errors.append(
                    f"  Scene {scene_no}: cue '{cue}' not found in narration words"
                )
    if errors:
        msg = "CUE VALIDATION FAILED — cue word not spoken in narration:\n" + "\n".join(errors)
        raise SystemExit(msg)
    print(f"✓ Cue validation passed for {len(scenes)} scene(s)")


def _resolve_cue_real(word_list, cue, preferred_start, scene_offset):
    """Resolve a cue word to absolute (start, end) using spoken word timestamps."""
    cue_norm = cue.lower().strip(".,!?:;\"'")
    matches = [
        w for w in word_list
        if w["word"].lower().strip(".,!?:;\"'") == cue_norm
    ]
    if not matches:
        return None
    if preferred_start is not None:
        rel_pref = preferred_start - scene_offset
        matches.sort(key=lambda w: abs(w["start"] - rel_pref))
    w = matches[0]
    start = round(scene_offset + w["start"], 4)
    end = round(scene_offset + w["end"], 4)
    if end - start < 0.5:
        end = round(start + 0.5, 4)
    return start, end

def run():
    brief = _load_json(BRIEF_PATH, {})
    timings = _load_json(TIMINGS_PATH, {})
    manifest = _load_json(MANIFEST_PATH, DEFAULT_MANIFEST)
    scenes = manifest.get("scenes", [])
    if not scenes:
        raise SystemExit("No scenes in composition/assets/manifest.json")

    _validate_cues(scenes, timings)

    COMPOSITION_DIR.mkdir(parents=True, exist_ok=True)

    template = TEMPLATE_PATH.read_text()
    render_order = []

    for idx, scene in enumerate(scenes, 1):
        scene_no = scene["scene"]
        duration = _scene_duration(timings, scene_no)
        scene_offset = _scene_start(timings, scene_no)

        cfg = {
            "scene_index": idx - 1,
            "scene_title": scene.get("title", f"Scene {scene_no}"),
            "duration": duration,
            "fit_mode": scene.get("fit_mode") or brief.get("fit_mode", "contain"),
            "backdrop": scene.get("backdrop"),
            "assets": [],
            "text": scene.get("text", []),
            "lowerThird": None,
            "titleCard": scene.get("titleCard"),
            "endCard": scene.get("endCard"),
            "fonts": scene.get("fonts", []),
        }

        word_list = None
        for s in timings.get("scenes", []):
            if s["scene"] == scene_no:
                word_list = s.get("words", [])
                break

        for asset in scene.get("assets", []):
            cue = (asset.get("cue_word") or "").strip()
            cue_start = asset.get("start")
            cue_end = asset.get("end")
            if cue and word_list:
                resolved = _resolve_cue_real(word_list, cue, cue_start, scene_offset)
                if resolved:
                    cue_start, cue_end = resolved
            cfg["assets"].append({
                "src": asset.get("src"),
                "cue_word": cue,
                "start": round(cue_start, 4) if cue_start is not None else 0,
                "end": round(cue_end, 4) if cue_end is not None else duration,
                "fit": asset.get("fit") or cfg["fit_mode"],
                "pan_x": asset.get("pan_x", 0),
                "pan_y": asset.get("pan_y", 0),
                "zoom": asset.get("zoom", 0.03),
            })

        if brief.get("show_section_titles") and scene.get("lowerThird"):
            lt = dict(scene["lowerThird"])
            lt["show_seconds"] = min(lt.get("show_seconds", 2), 2)
            cfg["lowerThird"] = lt

        injected = template.replace(
            'window.__SCENE_CONFIG__ || {};',
            f'window.__SCENE_CONFIG__ = {json.dumps(cfg)};'
        )
        scene_html = COMPOSITION_DIR / f"scene_{scene_no:02d}.html"
        scene_html.write_text(injected)

        render_order.append({
            "scene": scene_no,
            "file": f"scene_{scene_no:02d}.html",
            "duration": duration,
            "start_sec": round(scene_offset, 4),
            "end_sec": round(scene_offset + duration, 4),
        })
        print(f"  → scene_{scene_no:02d}.html  ({duration:.2f}s)")

    index_cfg = {"scene_index": 0, "scene_title": "Composition", "duration": 10}
    index = template.replace(
        'window.__SCENE_CONFIG__ || {};',
        f'window.__SCENE_CONFIG__ = {json.dumps(index_cfg)};'
    )
    (COMPOSITION_DIR / "index.html").write_text(index)

    (COMPOSITION_DIR / "render_order.json").write_text(json.dumps(render_order, indent=2))
    total = sum(r["duration"] for r in render_order)
    print(f"\n✓ Composition written to {COMPOSITION_DIR}")
    print(f"  Scenes: {len(render_order)} | Total: {total:.2f}s")
    return render_order


if __name__ == "__main__":
    run()
