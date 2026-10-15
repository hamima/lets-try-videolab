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
# Image-to-video pricing for wan-2.6 is $0.10/s at 720p vs $0.15/s at 1080p (the
# implicit default when "resolution" is omitted). 480p is not a valid option for
# image-to-video on this model (only "720p"/"1080p" are in supported_resolutions
# per GET /api/v1/videos/models), so 720p is the cheapest usable tier.
VIDEO_MODEL_RESOLUTION = "720p"
# "google/gemini-3.1-flash-tts" (no "-preview" suffix) does not exist on OpenRouter.
# Verified against GET /api/v1/models?output_modalities=speech.
TTS_MODEL   = "google/gemini-3.1-flash-tts-preview"
TTS_VOICE   = "Kore"
MUSIC_MODEL = "google/lyria-3-clip-preview"
