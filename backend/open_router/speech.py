"""backend/open_router/speech.py — Text-to-speech via OpenRouter's Audio API."""

import subprocess
import tempfile
import wave
from pathlib import Path

from . import client, models

# Google Gemini TTS models only support response_format "pcm" (raw 24kHz mono
# 16-bit samples, no container) — requesting "mp3" returns a 400 Bad Request.
_PCM_ONLY_PREFIXES = ("google/gemini",)

_PCM_SAMPLE_RATE = 24000
_PCM_CHANNELS = 1
_PCM_SAMPLE_WIDTH = 2  # bytes (16-bit)


def _pcm_to_mp3(pcm_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = Path(tmpdir) / "audio.wav"
        mp3_path = Path(tmpdir) / "audio.mp3"

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(_PCM_CHANNELS)
            wav_file.setsampwidth(_PCM_SAMPLE_WIDTH)
            wav_file.setframerate(_PCM_SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path), str(mp3_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed to transcode OpenRouter TTS output to mp3: {result.stderr}")

        return mp3_path.read_bytes()


def generate_speech(
    text: str,
    api_key: str,
    model: str = models.TTS_MODEL,
    voice: str = models.TTS_VOICE,
) -> bytes:
    pcm_only = model.startswith(_PCM_ONLY_PREFIXES)
    response_format = "pcm" if pcm_only else "mp3"

    resp = client.post(
        "/audio/speech",
        api_key,
        json={"model": model, "input": text, "voice": voice, "response_format": response_format},
    )

    if pcm_only:
        return _pcm_to_mp3(resp.content)
    return resp.content
