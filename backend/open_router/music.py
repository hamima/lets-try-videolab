"""
backend/open_router/music.py — Music generation via OpenRouter's audio-modality
chat completions (no dedicated music REST endpoint exists yet).

Audio output on OpenRouter requires streaming; audio bytes arrive as base64
chunks in each SSE chunk's choices[0].delta.audio.data field.
"""

import base64
import json

from . import client, models


def generate_music(
    prompt: str,
    api_key: str,
    model: str = models.MUSIC_MODEL,
    duration_seconds: int = 22,
) -> bytes:
    """Generate music from *prompt*. duration_seconds is unused for the
    clip-preview model, which always produces a fixed ~30s clip; kept for
    signature parity with the other open_router generators."""
    resp = client.post(
        "/chat/completions",
        api_key,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["text", "audio"],
            "audio": {"format": "mp3"},
            "stream": True,
        },
        stream=True,
        timeout=120,
    )

    chunks = bytearray()
    for line in resp.iter_lines():
        if not line or not line.startswith(b"data: "):
            continue
        payload = line[len(b"data: "):]
        if payload.strip() == b"[DONE]":
            break
        event = json.loads(payload)
        audio = event.get("choices", [{}])[0].get("delta", {}).get("audio")
        if audio and audio.get("data"):
            chunks.extend(base64.b64decode(audio["data"]))

    if not chunks:
        raise RuntimeError("OpenRouter music generation returned no audio data")
    return bytes(chunks)
