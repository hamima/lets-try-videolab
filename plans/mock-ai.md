# Mock All AI Generation Calls

Mock every external AI/API call in the VidLife pipeline so the full pipeline can run
end-to-end without spending API credits or requiring live services. This unblocks UI and
pipeline-flow development. The mock is toggled via a `MOCK_AI` boolean in `settings.json`
and the Settings UI.

**Key decisions:**
- Toggle lives in `settings.json` (existing settings system), readable at runtime via `_cfg()`
- Gemini text steps return per-step realistic fixture files (topic: "The History of the Internet")
- Binary outputs (images, audio, video) are generated on the fly with PIL / ffmpeg — no committed binaries
- RunPod animation mock writes the placeholder MP4 directly; no fake HTTP server
- `_fetch_real_image` mock writes a placeholder PNG directly to the asset directory
- All fixture text outputs must be structurally valid so downstream parsing steps work (scene plan format, EDL JSON, etc.)

---

## Add MOCK_AI toggle to settings

Extend the existing settings system with a `MOCK_AI` boolean field so it is readable
via `_cfg()` in `tasks.py` and controllable from the Settings UI without restarting
the server.

### Extend `backend/settings.py`
- Add `{"key": "MOCK_AI", "label": "Mock AI (dev mode)", "secret": False, "type": "bool"}` to `SETTINGS_KEYS`
- Update `load()` to cast `MOCK_AI` to `bool` (stored as JSON boolean in settings.json)
- Update `save()` to accept and persist boolean values correctly

### Add helper in `backend/tasks.py`
- Add `def MOCK_AI() -> bool: return bool(_cfg().get("MOCK_AI", False))` alongside the other key accessors

---

## Write fixture files for Gemini text steps

Create `backend/mocks/fixtures/` with one fixture file per Gemini-powered step.
All fixtures cover the topic "The History of the Internet". Each file must be
structurally valid so the pipeline parser for that step does not break.

### `research_dossier.md`
Realistic multi-section research document in ALL-CAPS section header format (parseable
by `_parse_sections`). Sections: OVERVIEW, KEY TIMELINE, MAJOR FIGURES, CONTROVERSIES,
SOURCES. ~400 words.

### `story_script.md`
3-minute documentary script in section format: HOOK, ACT 1, ACT 2, ACT 3, CLOSING.
~350 words.

### `scene_plan.md`
Valid scene plan in `SCENE N / Narration: / Duration: / Purpose: / Emotion:` format
(parseable by `_parse_scene_plan`). 5 scenes, 2 beats each. Duration values sum to ~3 min.

### `asset_manifest.md`
Valid asset manifest in `### SCENE N / **N.M** / KEY: value` format (parseable by
`_parse_asset_manifest`). One asset per beat. Mix of `TYPE: ai_image` and `TYPE: real_image`.
Include `KEN_BURNS:`, `VISUAL_GOAL:`, `DURATION:` fields.

### `asset_acquisition.md`
Valid acquisition doc in `SCENE N / ASSET N.M / LABEL:\nvalue` format (parseable by
`_parse_asset_acquisition`). Matches the assets declared in `asset_manifest.md`.
AI assets get `AI_PROMPT:` values; real assets get `SEARCH_QUERY:` values.

### `narration_script.txt`
Narration text with `=== ELEVENLABS VERSION ===` separator. Human-readable narration
above, TTS-optimised version below. ~200 words.

### `music_prompt.txt`
Short ElevenLabs-style music prompt describing a documentary score. ≤450 chars.

### `animation_prompt_template.txt`
Generic animation prompt used for each asset's `animated.txt`. Single paragraph,
≤100 words, with `{{ken_burns}}` and `{{visual_goal}}` placeholders replaced at mock time.

### `edl.json`
Valid EDL JSON that the `assemble.py` script can consume. Must reference the asset
paths that the fixture pipeline produces (scene_1/asset_1/animated.mp4 etc.).
5 scenes, matching `scene_plan.md` durations.

### `platform_metadata.json`
YouTube/social metadata: `title`, `description`, `tags`, `thumbnail_prompt`. Valid JSON.

---

## Create mock binary generators

Create `backend/mocks/generators.py` with three generator functions used by the mocked
step runners. All generators require only PIL (already available) and ffmpeg (already used
by `assemble.py`).

### `generate_placeholder_image(path: Path) -> None`
- Use PIL to create a 512×512 gray RGBA image
- Draw "MOCK IMAGE" centered in white text
- Save as PNG to `path`
- Fallback: if PIL not available, write a minimal valid 1×1 PNG bytestring

### `generate_silent_audio(path: Path, duration_seconds: float, fmt: str = "mp3") -> None`
- Call ffmpeg: `ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t {duration} {path}`
- Works for both `.mp3` and `.wav` output

### `generate_placeholder_video(path: Path, duration_seconds: float = 5.0) -> None`
- Call ffmpeg to produce a black 1280×720 MP4 at 16fps:
  `ffmpeg -y -f lavfi -i color=c=black:size=1280x720:r=16 -t {duration} -c:v libx264 {path}`

---

## Wire mocks into `backend/tasks.py`

Add a mock branch to each AI-calling function. All mock branches are guarded by
`if MOCK_AI():`. No changes to the real code paths.

### Mock `_gemini_generate(prompt, model)`
- Import and call a `_mock_gemini(step_id, ws)` helper that maps the current step's
  output filename to the correct fixture file in `backend/mocks/fixtures/`
- Since `_gemini_generate` is called from multiple step runners, pass the step context
  via a thread-local or by refactoring callers to check `MOCK_AI()` before calling
- Recommended approach: add `if MOCK_AI(): return _load_fixture(step_id)` at the top
  of each `_run_gemini_step`, `_run_animation_prompt_step` call site

#### `_load_fixture(step_id: str) -> str`
Helper in `tasks.py` (or imported from `mocks/`) that maps step ID → fixture filename
and returns the file contents. For step 8 (animation prompt), returns the template with
placeholders substituted with sensible defaults.

### Mock `_run_imagen_generation`
- At the top of `_run_imagen_generation`, after `if MOCK_AI():`:
  - For each `generated.txt` without an `image.png`: call `generate_placeholder_image(out_img)`
  - For each `search_query.txt` without an `image.jpg`: call `generate_placeholder_image(out_img.with_suffix('.jpg'))` — rename to `.jpg` for compatibility

### Mock `_run_elevenlabs_tts`
- At the top of `_run_elevenlabs_tts`, after `if MOCK_AI():`:
  - Call `generate_silent_audio(ws / "narration.mp3", duration_seconds=10.0, fmt="mp3")`
  - Return early

### Mock `_run_elevenlabs_music`
- At the top of `_run_elevenlabs_music`, after `if MOCK_AI():`:
  - Call `generate_silent_audio(ws / "music.wav", duration_seconds=22.0, fmt="wav")`
  - Return early (skip the ffmpeg extension loop — mock is already long enough)

### Mock `_run_runpod_animation`
- At the top of `_run_runpod_animation`, after `if MOCK_AI():`:
  - Iterate over all `animated.txt` files in the assets dir
  - For each one without an `animated.mp4` sibling, call `generate_placeholder_video(out_mp4)`
  - Return early

### Mock `_fetch_real_image`
- At the top of `_fetch_real_image`, after `if MOCK_AI():`:
  - Call `generate_placeholder_image(out_img)` where `out_img = out_dir / "image.jpg"`
  - Return `True`

---

## Add MOCK_AI toggle to the frontend Settings UI

The Settings panel already renders fields from `GET /tasks/settings`. Extend it to
render a boolean toggle for `MOCK_AI`.

### Backend schema change (in `settings.py`)
- Add `"type": "bool"` to the MOCK_AI field descriptor so the frontend can distinguish
  it from string fields

### Frontend Settings component
- In the Settings panel, detect `field.type === "bool"` and render a checkbox/toggle
  instead of a text input
- On save, send `MOCK_AI: true/false` (JSON boolean) in the PUT body
- Display a visible warning badge ("AI MOCK MODE ON") in the header or pipeline view
  when `MOCK_AI` is true, so it's obvious during development
