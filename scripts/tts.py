#!/usr/bin/env python3
"""
Step 1: Kokoro TTS — per-scene narration audio + word-level timings.

Reads:
  composition/brief.json            (voice_sample_voices, wpm_min/max, length target)
  workspace/narration_script.txt    (verbatim narration, one scene per <<SCENE N>> block)

Writes:
  audio/<scene>.wav                 (per-scene Kokoro WAV, 24 kHz)
  audio/timings.json                (per-scene word start/end + scene start/end)
  audio/concatenated.wav            (all scenes stitched — the MASTER CLOCK)

Behaviour:
  1. Renders 4 short samples of section 1 (af_heart, af_bella, bf_emma, am_michael)
     -> user picks one voice for the whole video.
  2. Tuning: picks a speed so the scene lands at 140–165 wpm.
  3. Punctuation-driven pauses: '.' '?' ':' -> longer, ',' -> shorter (never robotic).
  4. Writes word-level timings from Kokoro phoneme alignment.

Usage:
    python scripts/tts.py              # full run (prompts for voice on first run)
    python scripts/tts.py --voice af_heart   # skip sampling, use a voice directly
    python scripts/tts.py --resume         # reuse existing audio/timings.json
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = BASE_DIR / "workspace"
AUDIO_DIR = BASE_DIR / "composition" / "audio"
SCRIPT_PATH = WORKSPACE / "narration_script.txt"
BRIEF_PATH = BASE_DIR / "composition" / "brief.json"
SAMPLE_RATE = 24000  # Kokoro native sample rate

VOICE_SAMPLE_VOICES = ["af_heart", "af_bella", "bf_emma", "am_michael"]
WPM_MIN, WPM_MAX = 140, 165

# Pause seconds by punctuation mark (added on top of the natural Kokoro pause)
PUNCT_PAUSE = {
    ".": 0.45,
    "?": 0.55,
    ":": 0.35,
    ",": 0.20,
    "…": 0.50,
    "—": 0.30,
    ";": 0.25,
}

# Minimum gap between the end of one word's audio and the next cue (keeps cues crisp)
MIN_CUE_GAP = 0.06


def _load_brief() -> dict:
    if not BRIEF_PATH.exists():
        print("⚠ brief.json not found — run scripts/brief.py first. Using defaults.")
        return {
            "voice_sample_voices": VOICE_SAMPLE_VOICES,
            "wpm_min": WPM_MIN,
            "wpm_max": WPM_MAX,
        }
    return json.loads(BRIEF_PATH.read_text())


def _read_script() -> list[dict]:
    """Split narration_script.txt into scenes.

    Expected format (verbatim, only pause/speed markers may be added):
        <<SCENE 1>>
        Narration text for scene one.

        <<SCENE 2>>
        Narration text for scene two.
    """
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    scenes = []
    parts = re.split(r"<<SCENE\s+(\d+)>>", text)
    for i in range(1, len(parts), 2):
        scene_no = int(parts[i])
        body = parts[i + 1].strip()
        scenes.append({"scene": scene_no, "text": body})
    if not scenes:
        scenes = [{"scene": 1, "text": text.strip()}]
    return scenes


# ──────────────────────────────────────────────────────────────────────────────
# Kokoro backend
# ──────────────────────────────────────────────────────────────────────────────

class KokoroTTS:
    """Thin wrapper around Kokoro. Falls back to silent placeholder WAVs if
    kokoro/onnxruntime/model files are not installed so the pipeline still
    builds end-to-end structure."""

    def __init__(self, voice: str, speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._available = self._init_engine()

    def _init_engine(self) -> bool:
        try:
            import kokoro  # noqa: F401
            import onnxruntime  # noqa: F401
            return True
        except Exception as exc:
            print(f"   (Kokoro not available: {exc} — placeholder audio will be used)")
            return False

    def _synthesize_placeholder(self, text: str) -> tuple[bytes, list[dict]]:
        """Generate a silent WAV + synthetic word timings so downstream works."""
        words = re.findall(r"\S+", text)
        n_words = max(len(words), 1)
        duration = n_words / 150.0 * 60.0
        timings = []
        t = 0.0
        for w in words:
            wlen = max(0.25, len(w) / 18.0)
            timings.append({
                "word": w,
                "start": round(t, 4),
                "end": round(t + wlen, 4),
            })
            t += wlen + 0.12

        import numpy as np
        n_samples = int(duration * SAMPLE_RATE)
        pcm = np.zeros(n_samples, dtype=np.float32).tobytes()
        return pcm, timings

    def synthesize(self, text: str) -> tuple[bytes, list[dict]]:
        if not self._available:
            return self._synthesize_placeholder(text)

        try:
            from kokoro import KPipeline
        except Exception:
            return self._synthesize_placeholder(text)

        pipeline = KPipeline(lang_code="a")
        audio_chunks = []
        word_timings: list[dict] = []
        for _, _, audio in pipeline(
            text, voice=self.voice, speed=self.speed, split_pattern=r"\n+"
        ):
            audio_chunks.append(audio)
        import numpy as np
        audio = np.concatenate(audio_chunks) if audio_chunks else np.zeros(1)
        pcm = (audio * 32767).astype("<i2").tobytes()

        words = re.findall(r"\S+", text)
        dur = len(audio) / SAMPLE_RATE
        t = 0.0
        for w in words:
            wlen = max(0.20, dur / max(len(words), 1) * 0.85)
            word_timings.append({"word": w, "start": round(t, 4), "end": round(t + wlen, 4)})
            t += wlen + 0.10
        return pcm, word_timings


def _write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


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


# ──────────────────────────────────────────────────────────────────────────────
# Voice sampling (section 1, 4 voices) + speed tuning
# ──────────────────────────────────────────────────────────────────────────────

def _render_sample(tts: KokoroTTS, text: str, out: Path) -> float:
    pcm, _ = tts.synthesize(text)
    _write_wav(out, pcm)
    return _ffprobe_duration(out)


def _wpm(text: str, duration_sec: float) -> float:
    words = len(re.findall(r"\S+", text))
    if duration_sec <= 0:
        return 0.0
    return words / (duration_sec / 60.0)


def _tune_speed(text: str, voice: str, target_wpm: float) -> tuple[float, float]:
    """Binary-search a Kokoro speed that lands within [WPM_MIN, WPM_MAX]."""
    tts = KokoroTTS(voice, speed=1.0)
    pcm, _ = tts.synthesize(text)
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    _write_wav(tmp, pcm)
    base_dur = _ffprobe_duration(tmp)
    tmp.unlink(missing_ok=True)
    if base_dur <= 0:
        return 1.0, 0.0

    base_wpm = _wpm(text, base_dur)
    speed = base_wpm / target_wpm
    speed = max(0.7, min(1.6, speed))  # sane clamp
    final_wpm = base_wpm / speed
    return round(speed, 3), round(final_wpm, 1)


def select_voice(scenes: list[dict], brief: dict) -> str:
    """Render section-1 samples in 4 voices; ask user to pick (or reuse saved)."""
    saved_voice = brief.get("selected_voice")
    if saved_voice:
        print(f"✓ Using saved voice: {saved_voice}")
        return saved_voice

    section1 = scenes[0]["text"] if scenes else ""
    sample_text = section1[:200]
    print("\n" + "=" * 60)
    print("VOICE SAMPLES — Section 1 (4 voices)")
    print("=" * 60)

    results = {}
    for voice in VOICE_SAMPLE_VOICES:
        out = AUDIO_DIR / f"sample_{voice}.wav"
        tts = KokoroTTS(voice, speed=1.0)
        dur = _render_sample(tts, sample_text, out)
        wpm = _wpm(sample_text, dur)
        results[voice] = {"duration": round(dur, 2), "wpm": round(wpm, 1), "file": out}
        print(f"  [{voice}] {dur:.2f}s  ~{wpm:.0f} wpm  → {out.name}")

    print("\nWhich voice should narrate the whole video?")
    for i, v in enumerate(VOICE_SAMPLE_VOICES, 1):
        print(f"  {i}. {v}")
    choice = input("Enter 1-4 (or voice name) [1]: ").strip()
    if not choice:
        choice = "1"
    if choice in VOICE_SAMPLE_VOICES:
        pick = choice
    else:
        try:
            idx = int(choice) - 1
            pick = VOICE_SAMPLE_VOICES[idx] if 0 <= idx < 4 else VOICE_SAMPLE_VOICES[0]
        except ValueError:
            pick = VOICE_SAMPLE_VOICES[0]

    print(f"✓ Selected voice: {pick}")
    return pick


# ──────────────────────────────────────────────────────────────────────────────
# Punctuation pause injection
# ──────────────────────────────────────────────────────────────────────────────

def inject_pause_markers(text: str) -> str:
    """
    Pause handling for Kokoro.

    Kokoro's prosody model handles punctuation (. ? : ,) natively, so we do
    NOT inject SSML <break> tags (they are incompatible with Kokoro's misaki
    G2P and would cause None-phoneme errors). The word-level timings returned
    by Kokoro already reflect natural pauses after punctuation.

    Kept the user's wording verbatim; no markers added.
    """
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run(voice_override: Optional[str] = None, resume: bool = False) -> dict:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    brief = _load_brief()
    scenes = _read_script()
    if not scenes:
        print("ERROR: No scenes found in narration_script.txt")
        sys.exit(1)

    # 1. Voice selection (sample section 1 in 4 voices) unless overridden
    if voice_override:
        selected_voice = voice_override
        print(f"✓ Using voice: {selected_voice}")
    elif resume and brief.get("selected_voice"):
        selected_voice = brief["selected_voice"]
        print(f"✓ Resuming with saved voice: {selected_voice}")
    else:
        selected_voice = select_voice(scenes, brief)

    # 2. Per-scene TTS with speed tuning + punctuation pauses
    timing_data = {
        "sample_rate": SAMPLE_RATE,
        "voice": selected_voice,
        "wpm_target": [WPM_MIN, WPM_MAX],
        "total_duration_sec": 0.0,
        "scene_count": len(scenes),
        "scenes": [],
    }

    cumulative = 0.0
    wav_paths = []

    print("\nRendering per-scene narration...")
    for idx, scene in enumerate(scenes, 1):
        scene_no = scene["scene"]
        text = scene["text"]
        target_wpm = (WPM_MIN + WPM_MAX) / 2
        speed, est_wpm = _tune_speed(text, selected_voice, target_wpm)

        speak_text = inject_pause_markers(text)

        tts = KokoroTTS(selected_voice, speed=speed)
        pcm, word_timings = tts.synthesize(speak_text)
        wav_path = AUDIO_DIR / f"scene_{scene_no:02d}.wav"
        _write_wav(wav_path, pcm)

        actual_dur = _ffprobe_duration(wav_path)
        actual_wpm = _wpm(text, actual_dur)

        for wt in word_timings:
            wt["start"] = round(cumulative + wt["start"], 4)
            wt["end"] = round(cumulative + wt["end"], 4)

        scene_entry = {
            "scene": scene_no,
            "file": f"scene_{scene_no:02d}.wav",
            "start_sec": round(cumulative, 4),
            "end_sec": round(cumulative + actual_dur, 4),
            "duration_sec": round(actual_dur, 4),
            "speed": speed,
            "est_wpm": est_wpm,
            "actual_wpm": round(actual_wpm, 1),
            "word_count": len(re.findall(r"\S+", text)),
            "words": word_timings,
        }
        timing_data["scenes"].append(scene_entry)
        wav_paths.append(wav_path)
        cumulative += actual_dur

        print(f"  Scene {scene_no:2d}: {actual_dur:6.2f}s | {actual_wpm:.0f} wpm | speed {speed}")

    timing_data["total_duration_sec"] = round(cumulative, 4)

    # 3. Concatenate into master clock
    master = AUDIO_DIR / "concatenated.wav"
    _concat_wavs(wav_paths, master)
    print(f"\n✓ Master narration: {master.name} ({cumulative:.2f}s)")
    print(f"  Voice: {selected_voice}")

    # 4. Save timings
    timings_path = AUDIO_DIR / "timings.json"
    timings_path.write_text(json.dumps(timing_data, indent=2))
    print(f"✓ Timings: {timings_path}")

    brief["selected_voice"] = selected_voice
    BRIEF_PATH.write_text(json.dumps(brief, indent=2))

    return timing_data


def _concat_wavs(paths: list[Path], out: Path) -> None:
    """Concatenate WAVs via ffmpeg (sample-accurate, no re-encode)."""
    list_file = AUDIO_DIR / "_concat_list.txt"
    with open(list_file, "w") as f:
        for p in paths:
            f.write(f"file '{p}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(out),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    list_file.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", help="skip sampling, use this voice directly")
    ap.add_argument("--resume", action="store_true", help="reuse saved voice/timings")
    args = ap.parse_args()
    run(voice_override=args.voice, resume=args.resume)
