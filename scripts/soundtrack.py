#!/usr/bin/env python3
"""
Step 3: Soundtrack — mix voice + music into a broadcast-ready stereo WAV.

Reads:
  composition/audio/concatenated.wav      (voice — MASTER CLOCK)
  composition/audio/music.wav             (optional: your own music bed; skipped if absent)
  composition/brief.json                  (music_mood)

Writes:
  composition/audio/soundtrack.wav        (final mixed+mastered audio)

Voice chain: EQ → gentle compression → fixed gain → limiter.
Music: loudnorm to −24 LUFS → pad → trim to voice length → sidechain-ducked under voice
  (threshold 0.03, ratio 2.5, attack 200 ms, release 3500 ms).
Master: loudnorm to −16 LUFS, true peak ≤ −1 dBTP.

Usage:
    python scripts/soundtrack.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
COMPOSITION_DIR = BASE_DIR / "composition"
AUDIO_DIR = COMPOSITION_DIR / "audio"
BRIEF_PATH = COMPOSITION_DIR / "brief.json"
VOICE_PATH = AUDIO_DIR / "concatenated.wav"
MUSIC_PATH = AUDIO_DIR / "music.wav"
OUT_PATH = AUDIO_DIR / "soundtrack.wav"

TARGET_LUFS = -16
TRUE_PEAK = -1
MUSIC_LUFS = -24
VOICE_TO_MUSIC_GAP_LU = 17  # midpoint of 15–20 LU

# Sidechain ducking parameters
DUCK_THRESHOLD = 0.03
DUCK_RATIO = 2.5
DUCK_ATTACK = 200      # ms
DUCK_RELEASE = 3500    # ms


def _load_brief() -> dict:
    if not BRIEF_PATH.exists():
        return {}
    return json.loads(BRIEF_PATH.read_text())


def _ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return 0.0
    return float(r.stdout.strip())


def _measure_loudness(path: Path) -> dict:
    """Run ebur128 to get integrated loudness and true peak."""
    cmd = [
        "ffmpeg", "-i", str(path),
        "-af", "ebur128=peak=true",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stderr
    integrated = None
    true_peak = None
    for line in out.splitlines():
        if "I:" in line and "LUFS" in line:
            m = __import__("re").search(r"I:\s*([-\d.]+)", line)
            if m:
                integrated = float(m.group(1))
        if "TP:" in line:
            m = __import__("re").search(r"TP:\s*([-\d.]+)", line)
            if m:
                true_peak = float(m.group(1))
    return {"integrated": integrated, "true_peak": true_peak}


def run() -> dict:
    if not VOICE_PATH.exists():
        raise SystemExit(f"Voice file not found: {VOICE_PATH}")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    brief = _load_brief()
    voice_dur = _ffprobe_duration(VOICE_PATH)
    music_present = MUSIC_PATH.exists()

    print(f"Voice duration: {voice_dur:.2f}s | Music present: {music_present}")

    if music_present:
        # ── Two-input filtergraph: voice + sidechain-ducked music ──
        # Voice chain: EQ → gentle compression → fixed gain → limiter
        voice_chain = (
            "highpass=f=70,"
            "equalizer=f=120:t=h:w=1.4:g=-3,"      # gentle low cut rumble
            "equalizer=f=3000:t=h:w=1.0:g=1.5,"     # presence
            "acompressor=threshold=0.06:ratio=2.5:attack=15:release=180:makeup=1.1,"
            "volume=1.0,"                            # one fixed gain
            "alimiter=limit=0.88:attack=1:release=50"
        )
        # Music chain: normalize to −24 LUFS, pad head/tail, then trim to voice length
        music_chain = (
            f"loudnorm=I={MUSIC_LUFS}:TP={TRUE_PEAK}:LRA=7,"
            "apad=pad_dur=2,"
            f"atrim=0:{voice_dur},asetpts=PTS-STARTPTS"
        )
        # Sidechain duck music under voice, then mix, then master loudnorm
        filter_complex = (
            f"[0:a]{voice_chain}[voice];"
            f"[1:a]{music_chain}[music];"
            f"[music][voice]sidechaincompress="
            f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:"
            f"attack={DUCK_ATTACK}:release={DUCK_RELEASE}[music_ducked];"
            f"[voice][music_ducked]amix=inputs=2:duration=longest[mixed];"
            f"[mixed]loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11[out]"
        )
        inputs = ["-i", str(VOICE_PATH), "-i", str(MUSIC_PATH)]
        map_opt = ["-map", "[out]"]
    else:
        # ── Voice only ──
        voice_chain = (
            "highpass=f=70,"
            "equalizer=f=120:t=h:w=1.4:g=-3,"
            "equalizer=f=3000:t=h:w=1.0:g=1.5,"
            "acompressor=threshold=0.06:ratio=2.5:attack=15:release=180:makeup=1.1,"
            "volume=1.0,"
            f"alimiter=limit=0.88:attack=1:release=50,"
            f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"
        )
        filter_complex = f"[0:a]{voice_chain}[out]"
        inputs = ["-i", str(VOICE_PATH)]
        map_opt = ["-map", "[out]"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        *map_opt,
        "-c:a", "pcm_s24le",
        "-ar", "48000",
        str(OUT_PATH),
    ]

    print("Running ffmpeg soundtrack mix...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise SystemExit("ffmpeg soundtrack mix failed")

    loudness = _measure_loudness(OUT_PATH)
    out_dur = _ffprobe_duration(OUT_PATH)

    print(f"✓ Soundtrack: {OUT_PATH.name} ({out_dur:.2f}s)")
    print(f"  Integrated loudness: {loudness['integrated']} LUFS | True peak: {loudness['true_peak']} dBTP")

    return {
        "soundtrack": str(OUT_PATH),
        "duration": out_dur,
        "loudness_integrated": loudness["integrated"],
        "loudness_true_peak": loudness["true_peak"],
        "music_ducked": music_present,
    }


if __name__ == "__main__":
    run()
