#!/usr/bin/env python3
"""
Kokoro → HTML/GSAP → ffmpeg video pipeline orchestrator.

Runs the full chain:
  0. brief      (ask-once creative brief)
  1. tts        (Kokoro per-scene audio + word timings)
  2. compose    (build GSAP HTML compositions; validate cues)
  3. soundtrack (ffmpeg voice+music mix + loudnorm master)
  4. render     (HTML→silent MP4 → mux with soundtrack)
  5. checks     (lint, snapshots, loudness, STT audit)

Usage:
    python3 scripts/video_pipeline.py               # full run
    python3 scripts/video_pipeline.py --step tts    # run one stage
    python3 scripts/video_pipeline.py --voice am_michael --skip-checks
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Use the Framework Python (python3) which has kokoro/onnxruntime installed.
# `python` may resolve to Anaconda which lacks these packages.
PYTHON_EXE = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = BASE_DIR / "scripts"

STAGES = [
    ("brief",   "scripts/brief.py",           "Ask-once creative brief (composition/brief.json)"),
    ("tts",     "scripts/tts.py",             "Kokoro per-scene TTS + word timings"),
    ("compose", "scripts/compose.py",         "Build GSAP HTML compositions + cue validation"),
    ("soundtrack","scripts/soundtrack.py",   "ffmpeg voice+music mix + loudnorm master"),
    ("render",  "scripts/render.py",          "HTML→silent MP4 → mux with soundtrack"),
    ("checks",  "scripts/checks.py",          "Lint, snapshots, loudness, STT audit"),
]


def _run(stage_id, script, extra_args=None):
    # script paths in STAGES are relative to BASE_DIR (e.g. "scripts/brief.py")
    cmd = [PYTHON_EXE, str(BASE_DIR / script)]
    if extra_args:
        cmd += extra_args
    print(f"\n{'='*60}\nSTAGE: {stage_id}\n{'='*60}")
    r = subprocess.run(cmd, cwd=str(BASE_DIR))
    if r.returncode != 0:
        print(f"\n✗ Stage '{stage_id}' failed (exit {r.returncode})")
        sys.exit(r.returncode)
    print(f"✓ Stage '{stage_id}' complete")
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description="Kokoro→HTML→ffmpeg video pipeline")
    ap.add_argument("--step", help="run only this stage (brief|tts|compose|soundtrack|render|checks)")
    ap.add_argument("--voice", help="Kokoro voice to use (skip 4-voice sampling)")
    ap.add_argument("--resume", action="store_true", help="reuse saved voice/timings")
    ap.add_argument("--skip-checks", action="store_true", help="skip the checks stage")
    args = ap.parse_args()

    if args.step:
        ids = {s[0] for s in STAGES}
        if args.step not in ids:
            print(f"Unknown stage '{args.step}'. Valid: {', '.join(sorted(ids))}")
            sys.exit(1)
        todo = [s for s in STAGES if s[0] == args.step]
    else:
        todo = STAGES
        if args.skip_checks:
            todo = [s for s in todo if s[0] != "checks"]

    extra = []
    if args.voice:
        extra += ["--voice", args.voice]
    if args.resume:
        extra += ["--resume"]

    for stage_id, script, _desc in todo:
        stage_extra = list(extra)
        if stage_id == "checks":
            stage_extra = []  # checks takes no tts args
        _run(stage_id, script, stage_extra if stage_id == "tts" else [])

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("  Output: output/final_video.mp4")
    print("  Checks: checks/")
    print("=" * 60)


if __name__ == "__main__":
    main()
