"""
backend/open_router/models.py — Hardcoded OpenRouter model slugs.

The Settings UI only exposes the API key + the USE_OPENROUTER toggle;
which model backs each capability is a code-level decision, not a
user-configurable one.
"""

BASE_URL = "https://openrouter.ai/api/v1"

TEXT_MODEL  = "google/gemini-2.5-pro"
IMAGE_MODEL = "google/gemini-3.1-flash-image"
# Wan2.2-I2V-A14B (the open-weights model the self-hosted RunPod server runs) is not
# available on OpenRouter — alibaba/wan-2.6 is the closest Wan model OpenRouter hosts.
# Verified against GET /api/v1/videos/models. Only supports 5s or 10s clips.
VIDEO_MODEL = "alibaba/wan-2.6"
VIDEO_MODEL_SUPPORTED_DURATIONS = (5, 10)
# "google/gemini-3.1-flash-tts" (no "-preview" suffix) does not exist on OpenRouter.
# Verified against GET /api/v1/models?output_modalities=speech.
TTS_MODEL   = "google/gemini-3.1-flash-tts-preview"
TTS_VOICE   = "Kore"
MUSIC_MODEL = "google/lyria-3-clip-preview"
