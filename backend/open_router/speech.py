"""backend/open_router/speech.py — Text-to-speech via OpenRouter's Audio API."""

from . import client, models


def generate_speech(
    text: str,
    api_key: str,
    model: str = models.TTS_MODEL,
    voice: str = models.TTS_VOICE,
) -> bytes:
    resp = client.post(
        "/audio/speech",
        api_key,
        json={"model": model, "input": text, "voice": voice, "response_format": "mp3"},
    )
    return resp.content
