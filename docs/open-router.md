# OpenRouter.ai as an Alternative AI Provider

## Context

VidLife's pipeline (`backend/tasks.py`) normally calls Google Gemini (text), Google Imagen (images), a self-hosted Wan 2.2 I2V model on RunPod (video), and ElevenLabs (TTS + music) directly, with no abstraction layer. OpenRouter.ai is now available as a fully alternative, switchable AI backend, controlled by a single setting, so the whole pipeline can run against OpenRouter's models instead.

OpenRouter's Sept 2026 API surface has dedicated endpoints for every capability the app needs: text chat completions, image generation, image-to-video generation, TTS, and (via audio-modality chat completions) music generation. All 14 AI-calling steps in the 18-step pipeline are covered, not just the LLM-text steps.

Key decisions:
- **Single global toggle** (`USE_OPENROUTER` bool), not per-capability.
- **Settings UI only exposes the API key + the toggle** — no model picker. Models per capability are hardcoded in code.
- **New folder `backend/open_router/`** — a plain Python subpackage (colocated with `tasks.py`) responsible for all OpenRouter HTTP calls. No frontend changes were needed (Settings UI is fully data-driven from the backend).
- **Failure handling**: if an OpenRouter call fails, the step fails normally, matching each function's existing failure semantics (some steps are per-asset-lenient, some hard-fail). No automatic silent fallback to the self-hosted provider.
- **Code style**: matches the codebase's existing convention — every AI-calling function already starts with an `if MOCK_AI(): ...` early-exit branch. `if USE_OPENROUTER(): ...` branches were added the same way, rather than introducing a formal Provider interface/class hierarchy.

## Settings

Two entries added to `SETTINGS_KEYS` in `backend/settings.py`:

```python
{"key": "OPENROUTER_API_KEY", "label": "OpenRouter API Key", "secret": True},
{"key": "USE_OPENROUTER",     "label": "Use OpenRouter (alternative AI provider)", "secret": False, "type": "bool"},
```

Matching config getters in `backend/tasks.py`:

```python
def OPENROUTER_API_KEY() -> str:  return _cfg().get("OPENROUTER_API_KEY", "")
def USE_OPENROUTER()     -> bool: return bool(_cfg().get("USE_OPENROUTER", False))
```

Self-hosted-only settings (`RUNPOD_URL`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`) stay unchanged when `USE_OPENROUTER=true` — they're simply unread by the OpenRouter branches. `PEXELS_API_KEY`/`PIXABAY_API_KEY` remain in use regardless of the toggle (they back the non-AI real-image web-fetch path).

## The `backend/open_router/` package

Pure "HTTP calls to OpenRouter" package. Takes `api_key` as an explicit parameter and knows nothing about `settings.json` — `tasks.py` remains the only place that reads settings.

```
backend/open_router/
├── __init__.py     # empty, package marker
├── models.py       # hardcoded model-slug constants + BASE_URL
├── client.py       # shared HTTP/auth helper (requests-based)
├── text.py         # generate_text(prompt, api_key, model) -> str
├── image.py        # generate_image(prompt, api_key, model) -> bytes
├── video.py        # generate_video(image_path, prompt, api_key, duration_seconds, model) -> bytes
├── speech.py       # generate_speech(text, api_key, model, voice) -> bytes
└── music.py        # generate_music(prompt, api_key, model, duration_seconds) -> bytes
```

Imported the same way as the existing `backend/mocks` subpackage (`from open_router.text import generate_text`) — no `sys.path` tricks needed, since `tasks.py` is run with `backend/` as its own script directory.

### `models.py` — hardcoded model slugs

```python
BASE_URL = "https://openrouter.ai/api/v1"

TEXT_MODEL  = "google/gemini-2.5-pro"
IMAGE_MODEL = "google/gemini-3.1-flash-image"
VIDEO_MODEL = "alibaba/wan-2.6"  # closest Wan model OpenRouter hosts; Wan2.2-I2V-A14B (self-hosted) isn't on OpenRouter
TTS_MODEL   = "google/gemini-3.1-flash-tts-preview"  # no "-preview" suffix does not exist on OpenRouter
TTS_VOICE   = "Kore"
MUSIC_MODEL = "google/lyria-3-clip-preview"
```

### `client.py` — shared HTTP/auth helper

`post(path, api_key, **kwargs)` / `get(path, api_key, absolute=False, **kwargs)` inject `Authorization: Bearer <api_key>`, prefix `BASE_URL` (unless `absolute=True`, needed for OpenRouter's returned `polling_url`/`unsigned_urls`), and call `resp.raise_for_status()`. Before any HTTP call, a `RuntimeError` is raised if `api_key` is empty:

> "OpenRouter is enabled (USE_OPENROUTER=true) but OPENROUTER_API_KEY is missing. Add it in Settings."

This propagates through the step runner and is marked `"failed"` by the normal step-execution error handling — no special-case failure code needed.

### `text.py`

`POST /chat/completions` with `{"model", "messages": [{"role": "user", "content": prompt}]}` → `choices[0].message.content`.

### `image.py` — Unified Image API

`POST /images` with `{"model", "prompt"}`. Response:

```json
{"data": [{"b64_json": "<base64>", "media_type": "image/png"}], "usage": {...}}
```

`generate_image()` base64-decodes `data[0]["b64_json"]` and returns raw bytes.

### `video.py` — async image-to-video lifecycle

Encapsulates the full submit → poll → download lifecycle so the call site stays synchronous-looking, mirroring how `_run_runpod_animation()` already does inline polling against the self-hosted RunPod server:

1. If `model == models.VIDEO_MODEL` (the default `alibaba/wan-2.6`), round `duration_seconds` to the nearest value in `models.VIDEO_MODEL_SUPPORTED_DURATIONS` (`(5, 10)`) — this model only accepts 5s or 10s clips, unlike the self-hosted RunPod server which accepts arbitrary durations.
2. `POST /videos` with `model`, `prompt`, `duration`, and `frame_images: [{"type": "image_url", "image_url": {"url": <base64 data URI>}, "frame_type": "first_frame"}]` → `{id, polling_url, status: "pending"}`.
3. Poll `GET polling_url` (absolute URL) every `poll_interval` seconds until `status` is `completed`/`failed`/`cancelled`/`expired`, or raise `TimeoutError` after `max_wait_seconds` (default 600s, matching RunPod's `120 * 5s` budget).
4. On `completed`, download from `unsigned_urls[0]` (falls back to `{BASE_URL}/videos/{id}/content?index=0` if absent) and return raw MP4 bytes.

### `speech.py`

`POST /audio/speech` with `{"model", "input", "voice", "response_format"}` → raw audio bytes in the response body (non-JSON on success).

Google Gemini TTS models (matched by the `google/gemini` prefix) only support `response_format: "pcm"` — requesting `"mp3"` returns a 400. For those models, `generate_speech()` requests `"pcm"` (raw 24kHz mono 16-bit samples, no container), wraps the response in a WAV container via Python's `wave` module, and transcodes it to real MP3 via an `ffmpeg` subprocess call (mirroring the existing 210s-extension `ffmpeg` call in `_run_elevenlabs_music()`). Non-Gemini TTS models keep using `"mp3"` directly. Either way, `generate_speech()` always returns MP3 bytes, so `tasks.py`'s `(ws / "narration.mp3").write_bytes(...)` call site needs no changes.

### `music.py` — audio-modality chat completions

No dedicated music REST endpoint exists on OpenRouter. Music models (e.g. Lyria 3) are chat models whose `output_modalities` include audio; audio output requires `stream: true`. Request: `POST /chat/completions` with `modalities: ["text", "audio"]`, `audio: {"format": "mp3"}`, `stream: true`. Audio arrives as base64 chunks in `choices[0].delta.audio.data` across SSE events; `generate_music()` concatenates and decodes them. `duration_seconds` is accepted for signature parity with the other generators but unused — the clip-preview model always produces a fixed ~30s clip.

## Wiring in `backend/tasks.py`

An `if USE_OPENROUTER(): ...` branch (same idiom as `if MOCK_AI(): ...`) was added to each of the following, preserving each function's existing failure semantics exactly:

- **`_gemini_generate()`** — highest-leverage change: covers 10 of the 14 AI steps in one place (used by `_run_gemini_step` for steps 1,2,3,4,5,10,12,16,18 and by `_run_animation_prompt_step` for step 8). Branches to `open_router.text.generate_text(prompt, api_key=OPENROUTER_API_KEY())`.
- **`_run_imagen_generation()`** (step 7) — branches only the Imagen pass; the Pexels/Pixabay real-image web-fetch pass is unrelated to the toggle and runs unchanged in both branches. Preserves the per-image `except Exception` → `blocked.txt` swallow behavior.
- **`regenerate_asset_image()`** — a separate duplicate call site for single-image regeneration via the UI's "regenerate image" button. Also branches on `USE_OPENROUTER()` so the toggle isn't silently ignored here.
- **`_run_runpod_animation()`** (step 9) — the per-asset input resolution (locating `static_asset`, building `final_prompt`, computing `duration_seconds`) was extracted into a shared `_resolve_animation_inputs()` helper used by both branches. Branches to `open_router.video.generate_video(...)`. Keeps the existing per-asset `except Exception: continue` behavior.
- **`_run_elevenlabs_tts()`** (step 11) — branches to `open_router.speech.generate_speech(...)`; no exception swallowing, matching the existing unguarded `raise_for_status()` propagation.
- **`_run_elevenlabs_music()`** (step 13) — branches only the `music.wav` acquisition (if/else); the trailing ffmpeg loop-extension-to-210s logic is provider-agnostic and runs for both branches unchanged.

`_dispatch()` needed no changes — it only routes by step type; each runner handles its own provider choice internally.

## Dependencies

`requests` was already used ad-hoc throughout `tasks.py` (and now in `backend/open_router/`) but wasn't pinned — added to `backend/requirements.txt`.

## Verification

Use the existing single-step endpoint `POST /tasks/runs/{domain}/{run_id}/steps/{step_id}` with `{"force": true}` against a workspace that already has upstream files populated (e.g. from a prior `MOCK_AI=true` run):

1. `PUT /tasks/settings` with `{"settings": {"USE_OPENROUTER": true, "OPENROUTER_API_KEY": "<key>"}}`.
2. **Text**: force-run step 10 (Narration Script) — cheapest single `_gemini_generate` call; confirm `done` status and inspect output content.
3. **Image**: ensure a `generated.txt` exists, force-run step 7; confirm `image.png` is produced.
4. **Video**: ensure `animated.txt` + `image.png` exist, force-run step 9; poll (budget up to 10 min); confirm `animated.mp4` is a valid video file.
5. **TTS**: ensure `narration_script.txt` exists, force-run step 11; confirm `narration.mp3` is produced.
6. **Music**: ensure `music_prompt.txt` exists, force-run step 13; confirm `music.wav` is produced and the ffmpeg 210s-extension step still runs.
7. **Failure-path check**: clear `OPENROUTER_API_KEY` (toggle still on), force-run any step, confirm it ends `"failed"` with the friendly missing-key message — proving there's no silent fallback.
8. **Regression check**: set `USE_OPENROUTER=false`, re-run the same steps with `force: true`, confirm the original Gemini/Imagen/RunPod/ElevenLabs paths are unaffected.

## Critical files

- `backend/tasks.py` — 5 step-runner functions + `_gemini_generate()` + `regenerate_asset_image()` have branches added.
- `backend/settings.py` — 2 entries added to `SETTINGS_KEYS`.
- `backend/open_router/` — all OpenRouter HTTP logic.
- `backend/requirements.txt` — `requests` pinned.
