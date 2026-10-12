# Bruno Collection for Testing OpenRouter Calls

Create a new top-level `bruno/` folder containing a single Bruno collection, `bruno/openrouter/`, that lets a developer manually fire every OpenRouter HTTP call the pipeline makes — one request per pipeline step, rather than one generic request per endpoint type.

## Key decisions from scoping

- **Scope**: `backend/tasks.py`'s `STEPS` list has 13 steps that call OpenRouter when `USE_OPENROUTER=true`: steps 1, 2, 3, 4, 5, 10, 12, 16, 18 all hit `POST /chat/completions` (via `_gemini_generate` → `open_router.text.generate_text`); step 7 hits `POST /images`; step 11 hits `POST /audio/speech`; step 13 hits `POST /chat/completions` (streaming, audio modality); step 9 hits `POST /videos` + a polling `GET` + a download `GET`. That's **15 request files** total.
- **Layout**: flat, numbered `.bru` files directly inside `bruno/openrouter/` (no per-step subfolders) — e.g. `01-research.bru`, `02-story-script.bru`, ... `09-video-submit.bru`, `09-video-poll-status.bru`, `09-video-download-content.bru`.
- **Text-step bodies**: for the 9 `/chat/completions` steps, inline the literal prompt text from `prompts/general/*.md` (the `general` domain) as the `content` field, placeholders and all. Bruno's `{{var}}` syntax is identical to the prompt files' own `{{var}}` placeholders, so defining matching environment variables makes each request auto-fill from the environment with zero scripting.
  - Exception: `general` has no `02b_platform_metadata.md` (used by step 18) — source that one request's body from `prompts/general_knowledge/02b_platform_metadata.md` instead, and note the gap in a comment (do not fix the missing-file issue in the actual pipeline; out of scope).
  - Exception: step 10's prompt (`10_narration.md`) uses `{{narration_only}}`, not `{{story_script}}` as `tasks.py`'s `inputs` dict implies — mirror the literal file content, not the backend's (currently mismatched) intent.
  - Exception: step 16's prompt (`16_creative_director.md`) contains **no** `{{...}}` placeholders at all — its request body is static text with no environment variables.
- **Non-text-step bodies** (image, speech, music, video submit): no source template file exists for these (they're assembled dynamically in Python), so hardcode a realistic static example body for each, pulled from example content already present in the prompt docs (e.g. the "GOOD AI IMAGE PROMPTS" example in `04_asset_planning.md`, the narration example in `10_narration.md`, the music example in `12_music.md`).
- **Video image input**: bake one tiny sample image into the request as a literal base64 `data:` URI string (self-contained `.bru` file, no external file dependency).
- **Auth**: set `Authorization: Bearer {{openrouter_api_key}}` once at the collection level in `bruno.json`/collection settings; all requests inherit it.
- **Secrets**: commit `bruno/openrouter/environments/local.bru.example` (base URL, model names, all non-secret vars, `openrouter_api_key` left empty) and add the real, working `bruno/openrouter/environments/local.bru` to `.gitignore`. Developers copy the example once and paste their real key in locally.

## Reference values gathered from the codebase

- `BASE_URL` = `https://openrouter.ai/api/v1` (`backend/open_router/models.py`)
- `TEXT_MODEL` = `google/gemini-2.5-pro`
- `IMAGE_MODEL` = `google/gemini-3.1-flash-image`
- `VIDEO_MODEL` = `alibaba/wan-2.6` (verified against `GET /api/v1/videos/models`; only supports 5s/10s durations)
- `TTS_MODEL` = `google/gemini-3.1-flash-tts-preview` (verified against `GET /api/v1/models?output_modalities=speech`; no "-preview" suffix does not exist), `TTS_VOICE` = `Kore`
- `MUSIC_MODEL` = `google/lyria-3-clip-preview`

---

## Scaffold the Bruno collection root

Set up the collection skeleton so Bruno recognizes `bruno/openrouter/` as a valid collection before any requests are added.

### Create `bruno/openrouter/bruno.json`

Standard Bruno collection manifest: `{"version": "1", "name": "OpenRouter", "type": "collection"}`.

### Create `bruno/openrouter/collection.bru`

Set collection-level auth to Bearer with token `{{openrouter_api_key}}`, so every request inherits it without repeating the header.

### Add `.gitignore` entry

Append `bruno/openrouter/environments/local.bru` to the repo root `.gitignore` (alongside the existing `settings.json`, `.env`, `.keys` entries), matching the project's existing secret-handling convention.

### Create `bruno/openrouter/environments/local.bru.example`

Committed template with all non-secret vars populated and `openrouter_api_key` left as an empty string:
- `base_url` = `https://openrouter.ai/api/v1`
- `openrouter_api_key` = `` (empty — fill in locally)
- `text_model`, `image_model`, `video_model`, `tts_model`, `tts_voice`, `music_model` — the values listed above
- Text-input vars, each defaulted to a placeholder reminder string (e.g. `"<paste topic here>"`): `topic`, `language`, `research_dossier`, `story_script`, `scene_plan`, `asset_manifest`, `narration_only`

**Acceptance criteria**: copying `local.bru.example` to `local.bru`, filling in `openrouter_api_key`, and selecting the "local" environment in Bruno is all that's needed before any request can be sent.

---

## Build the 9 text-completion step requests

Each file is a `POST {{base_url}}/chat/completions` with JSON body `{"model": "{{text_model}}", "messages": [{"role": "user", "content": "<inlined prompt text>"}]}`.

### `01-research.bru`

Body content = full literal text of `prompts/general/01_research.md`, preserving its `{{topic}}` and `{{language}}` tokens so Bruno substitutes them from the environment.

### `02-story-script.bru`

Body content = full literal text of `prompts/general/02_story.md` (contains `{{research_dossier}}`).

### `03-scene-breakdown.bru`

Body content = full literal text of `prompts/general/03_scene_breakdown.md` (contains `{{story_script}}`).

### `04-asset-manifest.bru`

Body content = full literal text of `prompts/general/04_asset_planning.md` (contains `{{scene_plan}}`). Useful for manually re-verifying the asset-manifest parsing fix already made in `backend/tasks.py`.

### `05-asset-acquisition.bru`

Body content = full literal text of `prompts/general/05_asset_aquisition.md` — note the existing filename typo in the `general` domain; use it as-is (contains `{{asset_manifest}}`).

### `10-narration-script.bru`

Body content = full literal text of `prompts/general/10_narration.md` (contains `{{narration_only}}` — not `{{story_script}}`; mirror the file exactly).

### `12-music-prompt.bru`

Body content = full literal text of `prompts/general/12_music.md` (contains `{{scene_plan}}`).

### `16-edit-decision-list.bru`

Body content = full literal text of `prompts/general/16_creative_director.md`. No environment variables needed — this file has no `{{...}}` placeholders.

### `18-platform-metadata.bru`

Body content = full literal text of `prompts/general_knowledge/02b_platform_metadata.md` (contains `{{story_script}}`). Sourced from `general_knowledge` instead of `general` since the `general` domain is missing this file.

**Acceptance criteria for this task**: with the `local` environment selected and text vars filled with real content, each of the 9 requests sends successfully and returns a 200 with a plausible completion in `choices[0].message.content`.

---

## Build the image generation request

### `07-ai-image-generation.bru`

`POST {{base_url}}/images` with JSON body `{"model": "{{image_model}}", "prompt": "<static example prompt>"}`. Use one of the "GOOD AI IMAGE PROMPTS" examples from `prompts/general/04_asset_planning.md` verbatim as the static example prompt (e.g. the vault-door prompt), including the required quality-tag and style-consistency suffixes described in that file.

**Acceptance criteria**: sends successfully, returns 200 with a non-empty `data[0].b64_json`.

---

## Build the speech generation request

### `11-narration-audio.bru`

`POST {{base_url}}/audio/speech` with JSON body `{"model": "{{tts_model}}", "input": "<static example narration line>", "voice": "{{tts_voice}}", "response_format": "mp3"}`. Use the short example line from `prompts/general/10_narration.md`'s "EXAMPLE OUTPUT" section (e.g. "Imagine a vault holding seventeen billion euros.") as the static input text.

**Acceptance criteria**: sends successfully, returns 200 with binary MP3 content (Bruno should show the response as audio/binary, not an error JSON).

---

## Build the music generation request

### `13-music-audio.bru`

`POST {{base_url}}/chat/completions` with JSON body `{"model": "{{music_model}}", "messages": [{"role": "user", "content": "<static example music prompt>"}], "modalities": ["text", "audio"], "audio": {"format": "mp3"}, "stream": true}`. Use the full "EXAMPLE OUTPUT" paragraph from `prompts/general/12_music.md` as the static content value.

**Acceptance criteria**: sends successfully; note in a comment at the top of the file that this is an SSE/streaming response (matching `backend/open_router/music.py`'s handling), so Bruno will show raw `data: {...}` chunks rather than a single JSON body — this is expected, not an error.

---

## Build the video generation requests (submit, poll, download)

Three chained requests mirroring `backend/open_router/video.py`'s submit → poll → download flow for step 9.

### `09-video-submit.bru`

`POST {{base_url}}/videos` with JSON body:
```json
{
  "model": "{{video_model}}",
  "prompt": "<static example animation prompt>",
  "duration": 5,
  "frame_images": [
    {"type": "image_url", "image_url": {"url": "<baked-in base64 PNG data URI>"}, "frame_type": "first_frame"}
  ]
}
```
- Static example animation prompt: craft one 1–3 sentence description in the style described by `prompts/general_knowledge/08_animation_prompt.md` (camera motion + visual content + cinematic mood), e.g. describing a slow push-in on a vault door.
- Baked-in image: generate one tiny (e.g. 8×8 or 16×16 px) solid-color PNG, base64-encode it, and embed as a literal `data:image/png;base64,...` string directly in the JSON body — fully self-contained, no external file reference.
- Add a post-response script (Bruno `script:post-response` block) that extracts `res.body.id` and `res.body.polling_url` into runtime variables (`bru.setVar("video_job_id", ...)`, `bru.setVar("video_polling_url", ...)`), so the next two requests can chain off this one automatically.

### `09-video-poll-status.bru`

`GET {{video_polling_url}}` (the runtime variable set by the submit request's post-response script). Mirrors `client.get(polling_url, api_key, absolute=True, timeout=30)` in `video.py`. Add a comment noting this request should be sent repeatedly (Bruno has no built-in polling loop) until `status` in the response is `completed`, `failed`, `cancelled`, or `expired`.

### `09-video-download-content.bru`

`GET {{base_url}}/videos/{{video_job_id}}/content?index=0` as the default URL (matching `video.py`'s fallback construction), with a comment noting that if the poll response included `unsigned_urls`, that URL should be used instead (paste it in manually, or extend the poll request's post-response script to capture it into a `video_content_url` variable and use that here instead).

**Acceptance criteria for this task**: submit returns a job id and polling URL that get stored as runtime vars; poll can be re-sent manually until the job completes; download then returns binary video content.

---

## Write collection README

### Create `bruno/openrouter/README.md`

Short usage doc covering:
- Prerequisite: Bruno app installed, collection opened by pointing Bruno at `bruno/openrouter/`.
- One-time setup: `cp environments/local.bru.example environments/local.bru`, then open the collection in Bruno, select the "local" environment, and paste a real OpenRouter API key into `openrouter_api_key`.
- For the 9 text-step requests: paste real upstream output (e.g. actual `research_dossier.md` content) into the corresponding environment variable before sending, to get realistic results instead of the placeholder text.
- For the video flow: send `09-video-submit`, then repeatedly send `09-video-poll-status` until the job completes, then send `09-video-download-content`.
- Note that `settings.json`'s real API keys must never be copied into a committed file — only into the gitignored `environments/local.bru`.
