"""
backend/open_router/models.py — Hardcoded OpenRouter model slugs.

The Settings UI only exposes the API key + the USE_OPENROUTER toggle;
which model backs each capability is a code-level decision, not a
user-configurable one.
"""

BASE_URL = "https://openrouter.ai/api/v1"

TEXT_MODEL  = "google/gemini-2.5-pro"
IMAGE_MODEL = "google/gemini-3.1-flash-image"
# Verify against GET /api/v1/models?output_modalities=video before relying on this in production.
VIDEO_MODEL = "wan/wan2.6-i2v-a14b"
TTS_MODEL   = "google/gemini-3.1-flash-tts"
TTS_VOICE   = "Kore"
MUSIC_MODEL = "google/lyria-3-clip-preview"
