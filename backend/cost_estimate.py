"""
backend/cost_estimate.py — Rough cost estimation for a pipeline run, based on
the user-selected duration range and video/image split (see GeneratePage's
duration/split sliders).

This is inherently approximate: true token counts aren't knowable before a
run actually executes. The formula below blends a few per-unit rates
(calibrated against real OpenRouter pricing, see comments below) into a
single $/minute figure per cost driver, following the same "plain constants
+ a small pure function" style as backend/open_router/models.py.

    total_cost = flat_overhead
               + narration_rate * total_minutes
               + video_rate * video_minutes
               + image_rate * image_minutes

Where:
    video_minutes = total_minutes * (video_split_percent / 100)
    image_minutes = total_minutes * (1 - video_split_percent / 100)
"""

# ─────────────────────────────────────────────────────────────
# Video (alibaba/wan-2.6, image-to-video, 720p — Step 9)
# ─────────────────────────────────────────────────────────────
# $0.10/second at 720p (see open_router/models.py's VIDEO_MODEL_RESOLUTION).
VIDEO_RATE_PER_MINUTE = 0.10 * 60  # $6.00/min

# ─────────────────────────────────────────────────────────────
# Static images (google/gemini-3.1-flash-image — Step 7)
# ─────────────────────────────────────────────────────────────
# Pricing: prompt $0.50/M tokens, completion (text) $3/M tokens, plus a
# per-image output cost of $0.00006 per "output-image-token". OpenRouter
# doesn't publish a direct $/image figure for this model, so we assume a
# single generated image tokenizes to ~1290 output tokens (Google's published
# image-tokenization figure for a ~1024x1024 Gemini image output).
IMAGE_PROMPT_TOKENS_PER_IMAGE = 150   # typical length of a Step 7 AI_PROMPT
IMAGE_OUTPUT_TOKENS_PER_IMAGE = 1290  # ~1024x1024 image, per Gemini's tokenizer
IMAGE_PROMPT_RATE = 0.50 / 1_000_000
IMAGE_OUTPUT_RATE = 0.00006
COST_PER_IMAGE = (
    IMAGE_PROMPT_TOKENS_PER_IMAGE * IMAGE_PROMPT_RATE
    + IMAGE_OUTPUT_TOKENS_PER_IMAGE * IMAGE_OUTPUT_RATE
)
# Each static image is held on screen for ~8s of Ken Burns pan/zoom before
# cutting to the next one, so a minute of "image" footage needs ~60/8 images.
IMAGES_PER_MINUTE = 60 / 8
IMAGE_RATE_PER_MINUTE = IMAGES_PER_MINUTE * COST_PER_IMAGE

# ─────────────────────────────────────────────────────────────
# Narration (google/gemini-3.1-flash-tts-preview — Step 11)
# ─────────────────────────────────────────────────────────────
# Pricing: prompt (input script text) $1/M tokens, completion (output audio)
# $20/M tokens. Assumes ~150 words/min narration pace, ~1.3 tokens/word for
# the input text, and Gemini's published audio-tokenization rate of ~25
# tokens per second of generated audio.
NARRATION_WORDS_PER_MINUTE = 150
TOKENS_PER_WORD = 1.3
AUDIO_TOKENS_PER_SECOND = 25
TTS_PROMPT_RATE = 1.0 / 1_000_000
TTS_COMPLETION_RATE = 20.0 / 1_000_000
NARRATION_RATE_PER_MINUTE = (
    NARRATION_WORDS_PER_MINUTE * TOKENS_PER_WORD * TTS_PROMPT_RATE
    + 60 * AUDIO_TOKENS_PER_SECOND * TTS_COMPLETION_RATE
)

# ─────────────────────────────────────────────────────────────
# Flat per-run overhead
# ─────────────────────────────────────────────────────────────
# Steps whose cost scales weakly with video duration — research, story
# script, scene breakdown, asset manifest, asset acquisition, music prompt,
# and platform metadata (all google/gemini-2.5-pro text calls) — are treated
# as a fixed per-run estimate based on typical token counts for a single
# run, rather than scaled by duration. Plus one flat music-generation call
# (google/lyria-3-clip-preview always produces a fixed ~30s clip regardless
# of requested duration — see generate_music()).
TEXT_PROMPT_RATE = 1.25 / 1_000_000
TEXT_COMPLETION_RATE = 10.0 / 1_000_000
FLAT_STEP_PROMPT_TOKENS = 14_500      # sum across research/story/scenes/manifest/acquisition/music-prompt/metadata
FLAT_STEP_COMPLETION_TOKENS = 9_800
MUSIC_FLAT_COST = 0.04
FLAT_OVERHEAD = (
    FLAT_STEP_PROMPT_TOKENS * TEXT_PROMPT_RATE
    + FLAT_STEP_COMPLETION_TOKENS * TEXT_COMPLETION_RATE
    + MUSIC_FLAT_COST
)


def estimate_cost(total_minutes: float, video_split_percent: int) -> float:
    video_minutes = total_minutes * (video_split_percent / 100)
    image_minutes = total_minutes * (1 - video_split_percent / 100)
    return (
        FLAT_OVERHEAD
        + NARRATION_RATE_PER_MINUTE * total_minutes
        + VIDEO_RATE_PER_MINUTE * video_minutes
        + IMAGE_RATE_PER_MINUTE * image_minutes
    )


def estimate_cost_range(duration_min_minutes: int, duration_max_minutes: int, video_split_percent: int) -> dict:
    return {
        "min_cost": round(estimate_cost(duration_min_minutes, video_split_percent), 2),
        "max_cost": round(estimate_cost(duration_max_minutes, video_split_percent), 2),
    }
