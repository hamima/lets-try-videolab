# Burned-In Subtitles for the Final Video (Pipeline Step 18)

VidLife's web app pipeline gets a new step 18, **Subtitles**, inserted right after step 17 (Final Assembly) and before the current step 18 (Platform Metadata, which shifts to step 19). It reads the already-assembled `output/final_video.mp4` plus the narration text/timing, writes a human-readable, editable `subtitle.md` describing every caption and its timing, and burns those captions directly into `output/final_video.mp4` (overwriting it in place — a plain "Rerun" of step 17 regenerates a clean, caption-free copy if ever needed, exactly like reruns already work for every other step).

Key decisions from the interview:

- **Burn-in, not a sidecar file.** `subtitle.md` is a reviewable/editable intermediate artifact, not the deliverable itself — the deliverable is the subtitled `final_video.mp4`.
- **New step 18, not folded into step 17's `assemble.py`.** Keeps `assemble.py`'s already-dense EDL/scene logic untouched, and makes subtitle generation independently rerunnable without a full scene re-render.
- **Timing comes from ElevenLabs' native character-level alignment, not a new ML dependency.** Step 11 (Narration Audio) switches from ElevenLabs' plain `/v1/text-to-speech/{voice_id}` to its `/with-timestamps` variant, which returns character-level start/end timestamps in the same generation call — true forced alignment, free, same API, same key. When that data isn't available (OpenRouter TTS backend, or old pre-existing runs from before this feature), step 18 falls back to a pause-based heuristic using `narration_timing.json`'s existing per-scene `internal_pauses` data (already computed by step 15, zero new dependencies).
- **`subtitle.md` reuses this app's existing `SCENE N` / labelled-field "beat" convention** (the same shape `scene_plan.md` already uses), rather than an SRT-style format — it piggybacks on the existing `_parse_scene_plan`/`_parse_beats`-style parser pattern in `backend/tasks.py`, which also means the step gets an editable UI viewer for free, consistent with `scene_plan.md`/`asset_manifest.md`.
- **Caption chunking defaults**: max 2 lines, ~42 chars/line (~84 chars/caption), prefer breaking at sentence-ending punctuation, word-boundary wrap otherwise, 1–6 second duration clamp per caption. Standard subtitle-authoring conventions for this video's 1920×1080 resolution.
- **New dedicated bottom-center `subtitle` text style** — white text over a subtle semi-transparent bar, ~48px font, no flashy entrance/exit animation (existing `dramatic_center`/`stat_lower_third`/`name_tag` styles are all wrong fits for continuous dialogue captions).
- **Web-app-only.** `automate.py` maintains its own fully duplicated `STEPS` list and ElevenLabs TTS call, independent of `backend/tasks.py`. This plan only touches the actively-developed web app path; the CLI doesn't get subtitles unless someone separately ports this later.
- **Mock AI mode gets synthetic alignment data too**, not just the fallback path — so the primary (character-level) chunking logic is exercised by local/CI dev without real API keys, not just the heuristic fallback.
- **A real font gets sourced and committed.** `assemble.py` has pointed at a non-existent `fonts/NotoSansDevanagari-Bold.ttf` the whole time; every existing text overlay already silently degrades to PIL's tiny default font. Fixing this benefits subtitles *and* the pre-existing dramatic/lower-third/name-tag overlays.
- **Structural precedent**: the new step's core deterministic logic (parsing, chunking, scene-assignment) lives in an importable `backend/subtitles.py` module (unit-testable, no subprocess needed), with `scripts/generate_subtitles.py` as a thin subprocess entrypoint that imports it — exactly the `backend/workspace_migration.py` + `scripts/migrate_workspaces_to_users.py` split already established earlier in this project.

## Switch narration TTS to ElevenLabs' timestamps endpoint, with mock support

Step 11 (Narration Audio) needs to request and persist character-level alignment data alongside the audio it already generates, and Mock AI mode needs an equivalent synthetic version so the character-level caption logic is testable without real API keys.

### Switch `_run_elevenlabs_tts` to `/v1/text-to-speech/{voice_id}/with-timestamps`

In `backend/tasks.py`, change the real (non-mock, non-OpenRouter) ElevenLabs branch of `_run_elevenlabs_tts` (currently `tasks.py:786-796`) to call `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps` instead of the plain endpoint. That endpoint returns JSON (not raw audio bytes): `{"audio_base64": "...", "alignment": {"characters": [...], "character_start_times_seconds": [...], "character_end_times_seconds": [...]}, "normalized_alignment": {...}}`.

- Base64-decode `audio_base64` and write it to `narration.mp3` exactly as today.
- Write the `alignment` object (characters + start/end times) to a new `narration_alignment.json` in the workspace.
- Leave the `MOCK_AI` branch and the `USE_OPENROUTER` branch of this function untouched for now — no alignment file gets written on either of those paths (handled by Mock AI's own synthetic version below; OpenRouter has no equivalent and deliberately falls back at generation time in the new step).

#### Acceptance criteria
- A real (non-mock) run writes both `narration.mp3` (identical audio content as before) and a new `narration_alignment.json` with character-level start/end times covering the full narration text.
- The OpenRouter TTS path is unchanged and still produces `narration.mp3` with no alignment file.
- Existing step-11 tests (if any) still pass; add a unit test mocking the ElevenLabs response to verify both files get written correctly from a sample `with-timestamps` JSON payload.

### Add synthetic alignment data to Mock AI mode

In `mocks/generators.py` (or the mock-audio helper step 11 currently calls, `generate_silent_audio`), add a companion function/parameter that also writes a `narration_alignment.json` alongside the silent placeholder `narration.mp3` — evenly-spaced fake character timestamps spanning the placeholder's duration, built from the actual narration text in `narration_script.txt` so the character sequence is realistic (not literally the narration text is optional, but counts/spacing should look plausible).

Wire this into `_run_elevenlabs_tts`'s `MOCK_AI()` branch in `backend/tasks.py` so Mock AI runs always produce both files.

#### Acceptance criteria
- Running the pipeline with `MOCK_AI` on produces a `narration_alignment.json` with the same shape (`characters`/`character_start_times_seconds`/`character_end_times_seconds`) as the real ElevenLabs response.
- Step 18's primary (character-alignment) chunking path runs successfully end-to-end against Mock AI output, not just the fallback.

## Build the shared caption-segmentation module (`backend/subtitles.py`)

This is the pure, unit-testable core: turning either character-level alignment data or scene-level pause data into a list of timed, scene-grouped captions, plus the `subtitle.md` parser/serializer shared with the web app's editable viewer.

### Implement alignment-based chunking (primary path)

Add `backend/subtitles.py` with a function (e.g. `chunk_from_alignment(alignment: dict, scene_markers: list[tuple[int, int]]) -> list[Caption]`) that:
- Walks the character alignment data, grouping characters into words (via whitespace) and words into caption chunks respecting: max 2 lines, ~42 chars/line, preferring a break at sentence-ending punctuation (`.`/`!`/`?`) when a sentence fits within the limit, otherwise wrapping at the nearest word boundary.
- Clamps each resulting caption's duration to 1–6 seconds — merge adjacent sub-1s fragments into neighbors, and split/cap captions that would otherwise span a long pause beyond 6s.
- Assigns each caption to the correct scene number by cross-referencing the `[SCENE N]` markers' character offsets within the full TTS text (needed because `narration_script.txt`'s `[SCENE N]` headers mark scene boundaries in the *text*, while the alignment data is purely character-position-based — this cross-reference is what lets the character-level path still produce the scene-grouped `subtitle.md` format decided on below).

### Implement the pause-heuristic fallback (used when no alignment file exists)

Add a second function (e.g. `chunk_from_scene_timing(narration_timing: dict, scene_texts: dict[int, str]) -> list[Caption]`) that, for each scene in `narration_timing.json`:
- Splits that scene's narration text (extracted from the `[SCENE N]` block in `narration_script.txt`) into as many chunks as `len(scene["internal_pauses"]) + 1`, distributing sentences/words proportionally across chunks in reading order.
- Assigns each chunk a time window using the midpoints between consecutive `internal_pauses` (same midpoint convention `analyze_timing.py`'s `assign_scenes_to_silences` already uses for scene boundaries), with the scene's own `start_sec`/`end_sec` as the outer bounds.
- Applies the same 1–6 second duration clamp as the primary path for consistency.

Both functions return the same `Caption` shape (e.g. `{"scene_id": int, "start_sec": float, "end_sec": float, "text": str}`) so downstream code (serialization, burn-in) doesn't need to know which path produced them.

### Implement `subtitle.md` parsing and serialization

Add `parse_subtitles(text: str) -> list[Caption]` and `serialize_subtitles(captions: list[Caption]) -> str` to `backend/subtitles.py`, following the established `SCENE N` / labelled-field convention (mirroring `_parse_scene_plan`/`_parse_beats`/`_serialize_scene_plan` in `backend/tasks.py`):

```
SCENE 1

Start: 00:00:00,000
End: 00:00:03,400
Text: You bought it. You paid for it.
---
Start: 00:00:03,400
End: 00:00:06,800
Text: It's yours.
```

Timestamps are `HH:MM:SS,mmm` (SRT-style) for readability; `start_sec`/`end_sec` floats convert to/from this format via small helper functions in the same module.

#### Acceptance criteria
- `chunk_from_alignment` on a synthetic alignment fixture produces captions respecting the line-length/duration-clamp rules, correctly scene-tagged.
- `chunk_from_scene_timing` on a `narration_timing.json` fixture with multiple scenes and varying `internal_pauses` counts produces a sane chunk-per-scene split.
- `serialize_subtitles(parse_subtitles(text)) == text` round-trips for a representative fixture (same pattern as the existing `_parse_sections`/`_serialize_sections` tests).
- Edge cases covered: a scene with zero `internal_pauses` (single chunk), an empty/missing narration file, a caption that would otherwise exceed 6s getting split.

## Add the shared text-overlay module, bottom-center subtitle style, and font asset

### Extract `assemble.py`'s text-rendering helpers into a shared module

Move `render_text_overlay`, `apply_text_animation`, `apply_text_overlays`, `TEXT_STYLES`, and `FONT_PATH` out of `scripts/assemble.py` into a new `scripts/text_overlay.py`, imported by `assemble.py` unchanged (no behavior change for existing overlays) and by the new `scripts/generate_subtitles.py`. Avoids duplicating ~100 lines of Pillow rendering code and keeps one font/style source of truth.

### Add the `subtitle` style and a `bottom_center` position

In `scripts/text_overlay.py`'s `TEXT_STYLES`, add:
```python
"subtitle": {
    "font_size": 48,
    "color": (255, 255, 255, 255),
    "position": "bottom_center",
    "bg_type": "bar",
    "shadow": False,
},
```
Extend `render_text_overlay`'s position branching (currently `center`/`lower_left`/`top_right`) to handle `bottom_center`: horizontally centered, vertically anchored near the bottom with a safe margin (e.g. 100–140px from the bottom edge, matching the existing margin conventions used for `lower_left`).

### Source and commit a real font file

Download an open-license (SIL OFL) font with full Latin coverage — Noto Sans Devanagari Bold (keeps the existing `FONT_PATH` reference valid and covers Latin via Noto's shared Latin glyph set) or plain Noto Sans Bold if simpler — and commit it to `fonts/NotoSansDevanagari-Bold.ttf` (the path `assemble.py`/`text_overlay.py` already expects). Verify `ImageFont.truetype(FONT_PATH, ...)` succeeds instead of falling back to `ImageFont.load_default()`.

#### Acceptance criteria
- `assemble.py`'s existing overlays (dramatic/lower-third/name-tag) render identically to before the extraction (regression check via the existing `preview_ken_burns.py`-style manual preview, or a quick before/after frame diff).
- A new `bottom_center` caption renders horizontally centered with legible contrast against varied footage (bar background).
- `FONT_PATH` resolves to a real, loadable font file; no more silent fallback to PIL's default bitmap font.

## Build `scripts/generate_subtitles.py` — the step 18 entrypoint

The subprocess entrypoint `backend/tasks.py`'s `_run_script` invokes for step 18, following the `scripts/analyze_timing.py`/`scripts/assemble.py` conventions (reads `WORKSPACE_DIR`/`BASE_DIR` env vars, no CLI args needed).

### Implement the script

- `sys.path.insert(0, str(BASE_DIR / "backend"))`, then `from subtitles import chunk_from_alignment, chunk_from_scene_timing, serialize_subtitles` (same pattern as `scripts/migrate_workspaces_to_users.py` importing `backend/workspace_migration.py`).
- Load `narration_script.txt` (for `[SCENE N]` markers and text) and `narration_timing.json` (always required — scene boundaries).
- If `narration_alignment.json` exists, use `chunk_from_alignment`; otherwise fall back to `chunk_from_scene_timing`.
- Write `subtitle.md` via `serialize_subtitles`.
- Burn the captions into `output/final_video.mp4`: open it as a `VideoFileClip` (moviepy, imported from `scripts/text_overlay.py`'s dependencies), build one `ImageClip` per caption positioned at its absolute `start_sec`/`end_sec` (full-timeline, not per-scene-relative — simpler than re-deriving per-scene offsets since captions already carry absolute video-timeline seconds), composite with `CompositeVideoClip`, and overwrite `output/final_video.mp4` in place (write to a temp file first, then replace, to avoid corrupting the file on a failed/interrupted render).

#### Acceptance criteria
- Running the script against a workspace with a completed step 17 produces both a non-empty `subtitle.md` and an updated `output/final_video.mp4` with visibly burned-in bottom-center captions matching `subtitle.md`'s timing.
- A failed/interrupted render never leaves `output/final_video.mp4` corrupted or truncated (temp-file-then-replace).
- Running it against a workspace with no `narration_alignment.json` (OpenRouter TTS, or a pre-existing older run) still succeeds via the fallback path.

## Wire the new step into the web app backend

### Insert step 18 and renumber Platform Metadata to 19

In `backend/tasks.py`'s `STEPS` list (`tasks.py:93-112`), insert a new entry between the current steps 17 and 18:
```python
{"id": "18", "name": "Subtitles", "type": "script", "script": "generate_subtitles.py",
 "inputs": {"narration_script": "narration_script.txt", "narration_timing": "narration_timing.json"},
 "output": "subtitle.md"},
```
Bump the existing Platform Metadata entry's `"id"` from `"18"` to `"19"` (all its other fields — `prompt_file`, `inputs`, `output` — stay unchanged).

Update every other place keyed by these ids:
- `_FIXTURE_MAP` (`tasks.py:240-251`): move the `"18": "platform_metadata.json"` entry to `"19"`. The new step 18 is a `script` type (not `gemini`), so it doesn't need a fixture-map entry at all.
- `STEP_CONTENT_CONFIG` (`tasks.py:1661-1680`): add `"18": {"kind": "subtitles", "file": "subtitle.md"}`, move the existing `"18": {"kind": "json", "file": "platform_metadata.json"}` to `"19"`.

### Add the `subtitles` content kind to `get_step_content`/`update_step_content`

- `get_step_content`: add a branch for `kind == "subtitles"` that reads `subtitle.md` and returns `{"kind": "subtitles", "captions": parse_subtitles(text)}` (importing `parse_subtitles` from `backend/subtitles.py`).
- `update_step_content`: add `"subtitles"` to the tuple of editable kinds (`tasks.py:1935`), and a branch serializing an edited captions list back via `serialize_subtitles` before writing `subtitle.md`. Saving an edit only rewrites the file — it does **not** automatically re-trigger the burn-in render, consistent with how every other editable step already behaves (e.g. editing `scene_plan.md` doesn't auto-rerun step 4); re-burning requires an explicit Rerun of step 18.

#### Acceptance criteria
- `GET .../steps/18/content` on a run that has completed step 18 returns parsed, scene-grouped captions.
- `PUT .../steps/18/content` with edited captions correctly round-trips through `serialize_subtitles`/`parse_subtitles` and persists to `subtitle.md`.
- `GET .../steps/19/content` still returns Platform Metadata JSON exactly as it did at id 18 before this change — only the id moved, not the behavior.
- Full backend test suite (`pytest`) still passes after the renumbering, including existing tests that reference step ids by number (search and update any that hardcode `"18"` expecting Platform Metadata).

## Build the frontend Subtitle viewer and update mocks for the renumbered steps

### Add a `SubtitleViewer` component

Add `frontend/src/components/viewers/SubtitleViewer.tsx` (modeled on the existing scene-plan/research viewers), rendering the parsed captions grouped by scene with editable `start`/`end`/`text` fields per caption and a Save action calling the `PUT .../steps/18/content` endpoint. Add the corresponding `StepContent` union variant and types to `frontend/src/api/tasks.ts` (mirroring how `scene_plan`/`research` are already typed), and wire it into `StepContentPanel.tsx`'s kind-to-viewer dispatch.

### Update `frontend/src/mocks/handlers.ts` for the new/shifted steps

- `STEP_NAMES`/`STEP_TYPES`: add `'18': 'Subtitles'` / `'18': 'script'`, and move the existing Platform Metadata entries to `'19'`.
- `buildStepList`'s hardcoded `Array.from({ length: 18 }, ...)` → `19`.
- Move the existing `CONTENT[...]['18']` fixture blocks (political and science domains) to `'19'`, and add new `'18'` fixture blocks with representative mock subtitle captions for both domains.
- Update the `// Mock content — all 18 steps` comment to `19`.

#### Acceptance criteria
- `npx tsc --noEmit -p .` and `npm run build` both clean.
- With `VITE_MOCK_TASKS=true`, the Pipeline page shows 19 steps per run, step 18 is "Subtitles" with a working mock content panel, and step 19 is "Platform Metadata" exactly as step 18 behaved before this change.
- The Wizard view's step-reachability logic (`frontend/src/lib/wizard.ts`) correctly treats step 18 as sequential — no special-casing needed if the `STEPS`/mock data stay consistently ordered.

## Update documentation

- `README.md`: update the pipeline step list/count (18 → 19 steps, insert "Subtitles" into the enumerated flow) and the "Get the final video" section to mention burned-in captions.
- `docs/pipeline-overview.md`: add step 18 to the flow diagram/step table, renumber Platform Metadata to 19.
- `docs/tasks-api.md`: update the `STEP_CONTENT_CONFIG`/step reference table for the new `subtitles` kind and the renumbering.
- `docs/assembly.md`: document the new step 18 (inputs, outputs, burn-in behavior, fallback behavior) alongside the existing step 17/18(→19) documentation.
- `docs/audio-generation.md`: document step 11's switch to the ElevenLabs `/with-timestamps` endpoint and the new `narration_alignment.json` output.

#### Acceptance criteria
- No remaining reference anywhere in `docs/` or `README.md` to "18 steps" as the total, or to Platform Metadata as step 18.

## Tests and verification

- `backend/tests/test_subtitles.py` (new): unit tests for `chunk_from_alignment`, `chunk_from_scene_timing`, `parse_subtitles`/`serialize_subtitles` round-trip, and the edge cases listed under the segmentation task above.
- `backend/tests/test_parsers.py` or a new file: regression fixtures for the `SCENE N`/`Start`/`End`/`Text` format, same style as the existing bold/plain-label fixtures already in that file.
- Update any existing backend test that hardcodes step id `"18"` expecting Platform Metadata to use `"19"` instead (search `backend/tests/` for `"18"` before merging).
- Full verification pass: `cd backend && python -m pytest` (all green, including new tests); `cd frontend && npx tsc --noEmit -p . && npm run build` (clean).

#### Acceptance criteria
- Full backend suite and frontend typecheck/build both pass with zero regressions from the renumbering or the new step.
- A manual end-to-end run (real or Mock AI) against a fresh workspace produces a correct `subtitle.md` and a visibly captioned `output/final_video.mp4`.
