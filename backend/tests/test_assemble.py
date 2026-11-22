"""Tests for scripts/assemble.py: planning math, preflight, render + verifier."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "assemble.py"
spec = importlib.util.spec_from_file_location("assemble", SCRIPT)
asm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asm)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_workspace(tmp_path, slots, durations=None):
    """Scenes with distinct-luma solid-colour 2s clips (0.5s duration where short)."""
    ws = tmp_path / "ws"
    colors = ["0x202020", "0xd0d0d0", "0x707070", "0xf0f0f0", "0x404040"]
    total = slots[-1][1]
    edl, scenes = [], []
    for i, (a, b) in enumerate(slots, 1):
        d = ws / "assets" / f"scene_{i}" / f"asset_{i}.1"
        d.mkdir(parents=True)
        dur = (durations or {}).get(i, 2)
        ff("-f", "lavfi", "-i", f"color=c={colors[i - 1]}:s=640x360:r=24:d={dur}", str(d / "animated.mp4"))
        edl.append({"scene_id": i, "clips": [{"path": f"assets/scene_{i}/asset_1/animated.mp4",
                                              "type": "video", "duration_sec": 16, "effects": {}}],
                    "text_overlays": [], "sfx": []})
        scenes.append({"scene_id": i, "start_sec": a, "end_sec": b, "duration_sec": round(b - a, 3)})
    (ws / "edl.json").write_text(json.dumps(edl))
    (ws / "narration_timing.json").write_text(json.dumps(
        {"total_duration_sec": total, "scene_count": len(slots), "scenes": scenes, "all_silences": []}))
    ff("-f", "lavfi", "-i", f"sine=frequency=440:d={total}", "-ar", "44100", str(ws / "narration.mp3"))
    return ws


SLOTS = [(0.0, 1.25), (1.25, 2.5), (2.5, 4.0)]


def test_plan_uses_absolute_frames(tmp_path):
    ws = make_workspace(tmp_path, [(0.0, 0.34), (0.34, 0.67), (0.67, 1.0)])
    plan, tm, _ = asm.preflight(ws)
    # round(0.34*30)=10, round(0.67*30)=20 -> no cumulative drift
    assert [s["f0"] for s in plan["scenes"]] == [0, 10, 20]
    assert sum(s["n"] for s in plan["scenes"]) == plan["total_frames"] == 30


def test_preflight_rejects_bad_input(tmp_path):
    ws = make_workspace(tmp_path, SLOTS)
    t = json.loads((ws / "narration_timing.json").read_text())
    t["scenes"][1]["start_sec"] = 1.5  # gap/overlap
    (ws / "narration_timing.json").write_text(json.dumps(t))
    with pytest.raises(asm.PreflightError, match="gap|overlap"):
        asm.preflight(ws)

    ws = make_workspace(tmp_path / "b", SLOTS)
    t = json.loads((ws / "narration_timing.json").read_text())
    t["total_duration_sec"] = 9.0  # timing for a different audio file
    (ws / "narration_timing.json").write_text(json.dumps(t))
    with pytest.raises(asm.PreflightError, match="different audio"):
        asm.preflight(ws)

    ws = make_workspace(tmp_path / "c", SLOTS)
    e = json.loads((ws / "edl.json").read_text())
    e[0]["scene_id"] = 99
    (ws / "edl.json").write_text(json.dumps(e))
    with pytest.raises(asm.PreflightError, match="scene ids"):
        asm.preflight(ws)

    ws = make_workspace(tmp_path / "d", SLOTS)
    shutil.rmtree(ws / "assets" / "scene_2")
    with pytest.raises(asm.PreflightError, match="missing file"):
        asm.preflight(ws)


def test_render_is_exact_and_verifier_passes(tmp_path, monkeypatch):
    # scene 2's clip is only 0.5s but the slot is 1.25s -> must hold last frame
    ws = make_workspace(tmp_path, SLOTS, durations={2: 0.5})
    plan, tm, warns = asm.preflight(ws)
    assert any("FREEZE" in w for w in warns)
    out = tmp_path / "out.mp4"
    wav = asm.render(ws, plan, tm, out, tmp_path)
    assert asm.verify(out, plan, wav) == []


def test_verifier_catches_off_by_one_cut(tmp_path):
    ws = make_workspace(tmp_path, SLOTS)
    plan, tm, _ = asm.preflight(ws)
    out = tmp_path / "out.mp4"
    wav = asm.render(ws, plan, tm, out, tmp_path)
    assert asm.verify(out, plan, wav) == []

    # Claim scene 2 starts one frame later than it truly renders.
    import copy
    bad = copy.deepcopy(plan)
    bad["scenes"][1]["clips"][0]["f0"] += 1
    bad["scenes"][1]["clips"][0]["n"] -= 1
    assert asm.verify(out, bad, wav), "verifier should flag a shifted cut"


def test_overlays_punch_speed_multiclip(tmp_path):
    ws = make_workspace(tmp_path, SLOTS)
    e = json.loads((ws / "edl.json").read_text())
    c = e[2]["clips"][0]
    e[2]["clips"] = [dict(c, duration_sec=1, effects={"zoom_punch": {"at_sec": 0.3, "scale": 1.2, "duration_sec": 0.3}}),
                     dict(c, duration_sec=0.5, effects={"speed": 2.0})]
    e[0]["text_overlays"] = [{"text": "Hello", "style": "name_tag", "start_sec": 0.2, "end_sec": 1.0,
                              "animation": "fade_scale"}]
    (ws / "edl.json").write_text(json.dumps(e))
    plan, tm, _ = asm.preflight(ws)
    assert sum(c["n"] for c in plan["scenes"][2]["clips"]) == plan["scenes"][2]["n"]
    out = tmp_path / "out.mp4"
    wav = asm.render(ws, plan, tm, out, tmp_path)
    assert asm.verify(out, plan, wav) == []
