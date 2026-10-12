# OpenRouter Bruno Collection

Manual test requests for every OpenRouter HTTP call the VidLife pipeline makes (`backend/open_router/*.py`), one request per pipeline step.

## Prerequisites

- [Bruno](https://www.usebruno.com/) installed.
- Open the collection by pointing Bruno at this folder: `bruno/openrouter/`.

## One-time setup

1. Copy the environment template:
   ```
   cp environments/local.bru.example environments/local.bru
   ```
2. Open the collection in Bruno and select the **local** environment.
3. Paste a real OpenRouter API key into the `openrouter_api_key` variable.

`environments/local.bru` is gitignored — never commit it. Only `local.bru.example` (with the key left empty) is tracked in git.

**Never copy real keys from `settings.json` into a committed file.** Only paste them into the gitignored `environments/local.bru`.

## Text-completion steps (01, 02, 03, 04, 05, 10, 12, 16, 18)

Each request body inlines the literal prompt text from `prompts/general/*.md` (or `prompts/general_knowledge/02b_platform_metadata.md` for step 18, since the `general` domain is missing that file). The prompts' own `{{var}}` placeholders are resolved directly from the Bruno environment.

For realistic results instead of placeholder text, paste real upstream output into the corresponding environment variable before sending — e.g. paste an actual `research_dossier.md` into `research_dossier` before sending `03-scene-breakdown`.

`16-edit-decision-list.bru` has no environment variables to fill in — the prompt has no `{{...}}` placeholders.

## Non-text steps (07, 09, 11, 13)

These bodies are hardcoded with realistic static example content (no source template exists — the real pipeline assembles these dynamically in Python):

- `07-ai-image-generation.bru` — image generation, static example prompt
- `11-narration-audio.bru` — speech generation, static example narration line
- `13-music-audio.bru` — music generation. This is a **streaming SSE response** (matches `backend/open_router/music.py`), so Bruno will show raw `data: {...}` chunks rather than one JSON body — this is expected, not an error.

## Video generation flow (09a, 09b, 09c)

Three chained requests mirroring `backend/open_router/video.py`'s submit → poll → download flow:

1. Send **`09a - Video Submit`**. Its post-response script stores `video_job_id` and `video_polling_url` as runtime variables.
2. Send **`09b - Video Poll Status`** repeatedly (Bruno has no built-in polling loop) until the response's `status` is `completed`, `failed`, `cancelled`, or `expired`.
3. Send **`09c - Video Download Content`** to fetch the binary video content.

The submit request bakes in a tiny self-contained base64 PNG as the first-frame image — no external file dependency.
