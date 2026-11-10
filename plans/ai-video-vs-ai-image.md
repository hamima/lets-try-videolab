# Split AI-Generated Assets into `ai_video` (AI-animated) and `ai_image` (Ken-Burns)

Today every AI-generated static image — regardless of whether the asset manifest called it `ai_image` or `ai_video` — follows the exact same path: Step 7 generates `image.png`, Step 8 (`_run_animation_prompt_step`) calls Gemini to write a cinematic `animated.txt` motion description for it (gated only by a scene-level `Animate: yes/no` flag from Step 3), and Step 9 (`_animate_single_asset`) sends that image + prompt to an AI video model (OpenRouter `alibaba/wan-2.6` or self-hosted RunPod Wan2.2) to produce `animated.mp4`. There is no code path that actually renders a classic Ken-Burns pan/zoom in Python — `BURN_KEY_PREFIXES` only ever gets prepended as a text hint to the AI video prompt, and the only place real Ken-Burns math exists is a seemingly-dead MoviePy branch in `scripts/assemble.py`'s `build_single_clip()` for `clip_type == "image"`.

This plan makes `ai_video` and `ai_image` genuinely different asset types with different rendering pipelines:

- **`ai_image`** — a static AI-generated image, animated **in Python** via MoviePy using a Ken-Burns effect (`zoom_in` / `zoom_out` / `pan_left` / `pan_right`, with an `intensity` 0.1–0.3) for its full assigned `duration`. No AI video call, no Gemini-written motion prompt — Step 8 skips these assets entirely.
- **`ai_video`** — a static AI-generated image animated **by an AI video model** using a free-form (not Ken-Burns-templated) motion prompt written by Gemini in Step 8, for a duration snapped to the model's supported lengths (5s/10s).

Both produce an `animated.mp4` in the same asset folder by Step 9, so every downstream step (inventory, EDL/creative-director, final assembly) keeps treating every asset uniformly as `type: "video"` — this lets the EDL-driven Ken-Burns branch and `assemble.py`'s duplicate Ken-Burns implementation be deleted as dead code.

**Key decisions carried through every task below:**

- The existing scene-level `Animate: yes/no` field (Step 3 → Step 4 → Step 8 gate) is **removed entirely** and replaced by the ai_video/ai_image type decision made in Step 4 (Asset Manifest). This is now the single, unified mechanism for the video/image split — there is no parallel flag.
- The `{{video_split_percent}}` slider value (already wired end-to-end per the prior time-slider feature — see `docs/llm-steps.md`) now drives Step 4 instead of Step 3: **`video_split_percent`% of the TOTAL video duration** (not just the "eligible" pool) should be assigned `ai_video`, the remainder `ai_image` (which stays Ken-Burns-animated, never AI-animated — `ai_image`/`ai_video` are the only two asset types). To let the LLM target this numerically rather than just self-tracking from narration text, `backend/tasks.py`'s Step 4 runner computes the **total scene-plan duration in seconds** (summing all scene durations the same way `_duration_to_seconds()` already does per-asset) and injects both that total and the target `ai_video` second-count into the prompt as `{{total_duration_seconds}}` and `{{target_ai_video_seconds}}` — mirroring the existing special-casing pattern for Step 3 in `_run_gemini_step()` (`backend/tasks.py:299-306`), just one step further down.
- New manifest field `INTENSITY` (numeric, `0.1`–`0.3`, default `0.2` if the LLM omits/mis-formats it) is added alongside `KEN_BURNS`, giving the LLM per-scene control over how subtle/strong the Ken-Burns motion is (establishing shots subtler, dramatic reveals stronger) — mirrors the existing default-fallback pattern for `KEN_BURNS` itself, which also defaults (to `zoom_in`) rather than failing the step on a missing/invalid value.
- Because both `ai_video` and `ai_image` produce an `image.png` base file, filename-based type inference (the `name_to_type` dict in `_run_animation_prompt_step`) breaks down and is replaced by an explicit `asset_type` field persisted in `asset_meta.json`. **Step 6** (`_run_fetch_assets`) writes the full `asset_meta.json` (`asset_type`, `ken_burns`, `intensity`, `duration`) for **every** asset immediately as folders are created — carrying `KEN_BURNS`/`INTENSITY` through from Step 4's manifest via Step 5's acquisition doc, the same way `DURATION` already flows end-to-end today. Step 8 only adds/overwrites `animated.txt` for `ai_video` assets; Step 9 reads `asset_meta.json` directly to decide AI-call vs Ken-Burns-render, with no markdown re-parsing.
- Step numbering is unchanged — Steps 8 and 9 are reused with revised internal logic, not renumbered or split, since `STEPS_BY_ID`, `_output_exists()`'s `output_marker` checks, and the frontend's step-indexed UI all key off stable IDs.
- `zoom_punch` (the short emphasis-zoom applied per-clip in `assemble.py`) is unrelated to Ken Burns and is **kept as-is** — it's a separate end-of-pipeline effect layered on top of already-rendered `animated.mp4` clips, regardless of which rendering path produced them.
- `automate.py` (the older, separate CLI pipeline script) is **out of scope** — this plan only touches `backend/tasks.py` and its supporting prompts/scripts/tests/docs. No backward-compatibility shims are needed for manifests/state produced before this change, since the pipeline has no persisted-run migration requirement (per existing project convention of not supporting legacy formats).

## Rework the asset-planning and acquisition prompts for the ai_video/ai_image split

Update the Step 4 and Step 5 domain prompts (8 domain copies each) so the LLM makes an explicit, duration-aware choice between `ai_video` and `ai_image`, and carries the new `INTENSITY` field through.

### Update `04_asset_planning.md` (all 8 domains) with the new decision framework and fields

Insert a new decision step before the existing "EVERYTHING ELSE → ai_image" catch-all in the DECISION FRAMEWORK section (`prompts/{domain}/04_asset_planning.md`):

- New instruction block referencing `{{total_duration_seconds}}` and `{{target_ai_video_seconds}}`: "Across all scenes that would otherwise be ai_image, assign approximately `{{target_ai_video_seconds}}` seconds' worth (out of `{{total_duration_seconds}}` total) to `ai_video` instead — prioritize scenes with the strongest motion/visual potential (dramatic reveals, establishing shots with depth, scenes benefiting from camera movement beyond a simple zoom/pan) for `ai_video`; the rest stay `ai_image`."
- Update `OUTPUT FORMAT`'s `ASSET_TYPE` line to `(ai_video | ai_image)` — `ai_video` already appears in the allowed-type conversion table in `05_asset_acquisition.md` but was never actually offered as a distinct choice in Step 4's own output enum.
- Scope `KEN_BURNS` to non-`ai_video` types only: `KEN_BURNS: (zoom_in | zoom_out | pan_left | pan_right) — only for ai_image; N/A for ai_video`.
- Add a new `INTENSITY` field: `INTENSITY: (0.1-0.3, subtler for establishing shots, stronger for dramatic reveals) — only for ai_image; N/A for ai_video`.
- Remove the `ANIMATE: (yes | no — carry over...)` line entirely from the output format — this field no longer exists anywhere upstream (removed from Step 3, see below).
- Update the QUALITY CHECKLIST bullet "Ken Burns direction is specified for every ai_image scene" to also mention intensity, and leave the "At least 70% of scenes use ai_image" bullet as-is (still true — `ai_video` is carved out of the ai_image pool, not additive to it).

#### Apply identical edits across all 8 domain copies

`04_asset_planning.md` exists per-domain under `prompts/{political,general_knowledge,science,business,history,sports,technology,general}/`. Since the DECISION FRAMEWORK / OUTPUT FORMAT structure is identical across domains (only tone/examples differ), apply the same structural edit to each, preserving each domain's existing voice/example prompts.

### Remove the `Animate` field from `03_scene_breakdown.md` (all 8 domains)

Delete the `{{video_split_percent}}` injection and the "Animate (yes/no)" bullet, the "Mark approximately {{video_split_percent}}%..." paragraph, and the `Animate:` field from the SCENE 1 / SCENE 2 output template examples in `prompts/{domain}/03_scene_breakdown.md`. Step 3's prompt goes back to only needing `{{story_script}}` and `{{duration_range}}` — `{{video_split_percent}}` is no longer injected here at all.

### Confirm `05_asset_acquisition.md` carries `KEN_BURNS`/`INTENSITY` through unchanged

`prompts/{domain}/05_asset_acquisition.md` already lists `ai_video`/`ai_image` as the only two types with correct conversion rules (lines 33-42) and its `OUTPUT FORMAT` (lines 70-93) needs two additions mirroring how `DURATION` already passes through verbatim: add `KEN_BURNS:` and `INTENSITY:` fields to the output format (N/A for ai_video, carried-over value for ai_image), with the "Duration and priority must remain unchanged" rule in GENERAL RULES extended to cover these two fields as well ("Duration, priority, Ken Burns direction, and intensity must remain unchanged").

## Rewrite Step 6 to persist `asset_meta.json` for every asset at creation time

### Extend `_run_fetch_assets()` in `backend/tasks.py`

In `_parse_acquisition_doc()`'s per-asset dict, the new `ken_burns` and `intensity` fields parsed from `asset_acquisition.md` are already captured generically (the parser is field-name-agnostic — any `KEY: value` line becomes `asset[key.lower()]`), so no parser changes are needed there. In `_run_fetch_assets()` (`backend/tasks.py:366-425`), after the existing per-type branch (`ai_video`/`ai_image` → `generated.txt`), add an unconditional block that writes `asset_meta.json` for every asset:

```python
intensity_raw = a.get("intensity", "").strip()
try:
    intensity = float(intensity_raw)
    if not (0.1 <= intensity <= 0.3):
        intensity = 0.2
except ValueError:
    intensity = 0.2

ken_burns = a.get("ken_burns", "").strip().lower()
if ken_burns not in ("zoom_in", "zoom_out", "pan_left", "pan_right"):
    ken_burns = "zoom_in"

(out_dir / "asset_meta.json").write_text(json.dumps({
    "asset_type": atype,
    "ken_burns": None if atype == "ai_video" else ken_burns,
    "intensity": None if atype == "ai_video" else intensity,
    "duration": a.get("duration", "5 seconds"),
}, indent=2))
```

Place this after the existing type-specific `if/elif` chain so it runs for every branch (including `ai_image`, which gets Ken-Burns-animated, per the earlier "always Ken Burns for non-ai_video" decision).

### Update the `MOCK_AI` fixture-writing branch in the same function

The existing mock block (`backend/tasks.py:420-425`) unconditionally writes a fixed `asset_meta.json` (`{"ken_burns": "zoom_in", "duration": "5 seconds"}`) and an `animated.txt`/`animated.mp4` for every asset regardless of type. Update it to also set `"asset_type": atype` and `"intensity": 0.2`, and only write the mock `animated.txt` when `atype == "ai_video"` (Ken-Burns mock assets get their `animated.mp4` placeholder directly in Step 9's mock path instead — see next task — keeping mock-mode's step-by-step behavior aligned with real-mode's new per-type branching).

## Make Step 8 (`_run_animation_prompt_step`) `ai_video`-only

### Restrict asset discovery to `ai_video` assets via `asset_meta.json`

Rewrite `_run_animation_prompt_step()` (`backend/tasks.py:638-723`) to stop scanning for `image.png` by filename-based type inference and instead iterate `asset_meta.json` files under `assets_dir.rglob("asset_meta.json")`, skipping any whose `asset_type != "ai_video"`. This removes the `name_to_type` filename-inference dict entirely (`backend/tasks.py:702`) — `asset_type` is now read directly from the meta file instead of guessed from the base-image filename.

Remove the `animate == "no": continue` gate and the `_parse_asset_manifest()`-based lookup for `ken_burns`/`visual_goal`/`duration`/`animate` (the manifest no longer carries a per-asset `animate` flag, and `ken_burns`/`duration` are now sourced from `asset_meta.json`, which was written with the authoritative values at Step 6). `_parse_asset_manifest()` itself still has a purpose — it supplies `visual_goal` — so update it to drop the `animate` key from its parsed dict (`backend/tasks.py:601-635`) rather than removing the function.

### Update `08_animation_prompt.md` to drop the Ken-Burns translation table (all 8 domains)

Since Step 8 now only runs for `ai_video` assets (which never get an assigned `ken_burns` direction), remove the `{{ken_burns}}` input line and the entire "KEN BURNS TRANSLATION" mapping table from `prompts/{domain}/08_animation_prompt.md`. Replace the TASK instruction with free-form motion guidance: the model should invent camera movement purely from `{{visual_goal}}`, `{{duration}}`, and `{{story_excerpt}}` — e.g. "Based on the visual goal and the story's tone, invent camera motion that best serves this specific shot (push, pull, drift, orbit, rack focus, or a combination) — do not default to a generic zoom." Keep the "exactly 1-3 sentences" output constraint and duration-naturally-included instruction unchanged.

### Update the `MOCK_AI` branch of Step 8

The mock early-return in `_run_animation_prompt_step()` (`backend/tasks.py:639-652`) currently writes `animated.txt` + `asset_meta.json` for every `image.png` found. Scope it to only write `animated.txt` for assets whose `asset_meta.json` (already written by Step 6's updated mock branch) has `asset_type == "ai_video"`.

## Add the Python Ken-Burns renderer and make Step 9 branch by asset type

### Extract a shared Ken-Burns render function into `backend/ken_burns.py`

Create a new module `backend/ken_burns.py` containing a single function, extracted from the existing MoviePy logic in `scripts/assemble.py`'s `build_single_clip()` (`scripts/assemble.py:240-266`):

```python
from pathlib import Path
from moviepy import ImageClip

def render_ken_burns(image_path: Path, out_path: Path, direction: str, intensity: float, duration_seconds: float, width: int = 1920, height: int = 1080) -> Path:
    clip = ImageClip(str(image_path))
    # resize-to-fill logic reused from scripts/assemble.py's resize_to_fill()
    ...
    if direction == "zoom_in":
        clip = clip.resized(lambda t: 1.0 + intensity * (t / duration_seconds))
    elif direction == "zoom_out":
        clip = clip.resized(lambda t: (1.0 + intensity) - intensity * (t / duration_seconds))
    elif direction == "pan_left":
        ...
    elif direction == "pan_right":
        ...
    clip = clip.with_duration(duration_seconds)
    clip.write_videofile(str(out_path), fps=30, codec="libx264", audio=False)
    return out_path
```

Reuse `resize_to_fill()` from `scripts/assemble.py` (either duplicate the small helper or extract it alongside — it's a tight crop-to-aspect-ratio function with no other dependencies) so the output always matches the `1920x1080` target before Ken-Burns transforms are applied, consistent with `assemble.py`'s `TARGET_WIDTH`/`TARGET_HEIGHT` constants.

### Branch `_animate_single_asset()` by `asset_type`

Rewrite `_animate_single_asset()` (`backend/tasks.py:760-822`) to take the asset's directory (not just an `animated.txt` path, since Ken-Burns assets won't have one) and read `asset_meta.json` first:

- If `asset_type == "ai_video"`: keep the existing logic unchanged (resolve `animated.txt` + `asset_meta.json` via `_resolve_animation_inputs()`, call OpenRouter or RunPod).
- Else (`ai_image`): locate the static base file (`image.png`), call `render_ken_burns()` from `backend/ken_burns.py` with `ken_burns`/`intensity`/`duration` read straight from `asset_meta.json`, no Gemini involvement.
- In `MOCK_AI()` mode, keep writing a placeholder video via `generate_placeholder_video()` regardless of type (no behavior change needed there — mock mode doesn't care which renderer would have run).

Update the function signature and all call sites (`_run_runpod_animation()`, the `/animate` endpoint) accordingly — see next two subtasks.

### Update `_run_runpod_animation()` (Step 9 batch runner) to discover all animatable assets

Change the discovery loop in `_run_runpod_animation()` (`backend/tasks.py:825-838`) from `assets_dir.rglob("animated.txt")` to `assets_dir.rglob("asset_meta.json")`, skipping any asset directory where `animated.mp4` already exists (resumability, unchanged). This ensures Ken-Burns assets (which never get an `animated.txt`) are still picked up and rendered — previously only `ai_video`-style assets with a prompt file were found. Keep the existing best-effort "log/continue on exception" semantics per asset.

### Rename the misleading `_run_runpod_animation` / "Video Animation" step type if desired

Since the function now also renders plain Ken-Burns clips with no network calls, consider whether `"type": "runpod_animation"` in Step 9's `STEPS` entry (`backend/tasks.py:107`) and the function name should be renamed to something type-neutral (e.g. `"animate_assets"` / `_run_asset_animation()`). This is a pure rename for clarity — not required for correctness, since `_dispatch()` just maps the `type` string to the function regardless of naming — but keep it in scope since the current name actively misleads about what the step now does for Ken-Burns assets.

## Simplify the EDL/creative-director prompt and `assemble.py` now that every asset is a pre-rendered video

### Remove Ken-Burns and `ANIMATE` language from `16_creative_director.md` (all 8 domains)

Since every asset now arrives at Step 16 as an already-rendered `animated.mp4` (pre-rendered Ken-Burns or pre-rendered AI video), remove:
- The "For scenes with only images: apply Ken Burns effect (slow zoom or pan)" line from CREATIVE PRINCIPLES.
- The `"ken_burns": {"direction": "zoom_in", "intensity": 0.2}` field from the EDL v2 JSON schema example's `effects` object — collapse the example clip's `type` to always be `"video"`.
- The RULES bullet "For images (.jpg, .png, .webp): set type to 'image' and add ken_burns effect" and "Ken Burns options: {...}".
- The QUALITY CHECKLIST bullet "Ken Burns applied to all image clips."

Keep the `zoom_punch` sections (CREATIVE PRINCIPLES "ZOOM PUNCH" block, the EDL schema's `zoom_punch` field, and its QUALITY CHECKLIST bullet) completely unchanged — it remains a valid emphasis effect on top of `type: "video"` clips.

### Remove the dead Ken-Burns branch from `scripts/assemble.py`'s `build_single_clip()`

Delete the `clip_type == "image"` branch (`scripts/assemble.py:240-266`) entirely along with its Ken-Burns zoom/pan math — now redundant with `backend/ken_burns.py`'s pre-render step, and EDL clips will no longer have `type: "image"` once `16_creative_director.md` is updated. `build_single_clip()` becomes video-only (the existing "Video" branch below line 268 handles all clips uniformly).

### Simplify `scripts/generate_inventory.py` (Step 14) to list only `animated.mp4`

Since every asset is now backed by a single `animated.mp4` (no more raw `image.png`/`image.jpg` candidates competing for selection), simplify the inventory script's per-folder scan (`scripts/generate_inventory.py:98-103`) to only glob `*.mp4` rather than globbing images and videos together — removing the now-unreachable "STATUS: Prompt exists, asset not yet generated" branch and the image-only candidate paths, since Step 9 guarantees every asset folder has exactly one `animated.mp4` by the time Step 14 runs.

## Expose `asset_type` through the content API and scope the manual Animate button to `ai_video`

### Add `asset_type` to the `video_list` content builder

In the `kind == "video_list"` block of the step-content endpoint (`backend/tasks.py:1798-1835`), read each asset's `asset_meta.json` (already present for every asset since Step 6) and include `"asset_type": meta.get("asset_type")` in each returned item.

### Update `animation_list` / `assets_viewer` discovery to not rely solely on `animated.txt`

The `kind == "animation_list"` builder (`backend/tasks.py:1767-1796`) currently discovers assets by scanning for `animated.txt`, which will now only exist for `ai_video` assets — this view becomes `ai_video`-only by construction, which is correct (it's specifically an "animation prompt" viewer). No change needed here beyond confirming this is the intended, narrower scope post-change. The `assets_viewer` `FILE_LABELS` dict (`backend/tasks.py:1840-1848`) needs no changes — it already labels `animated.txt` generically as "Animation Prompt," which remains accurate.

### Gate the frontend Animate/Re-animate button on `asset_type`

In `frontend/src/components/viewers/VideoSceneViewer.tsx`, add `asset_type: string` to the `VideoItem` interface and thread it through from the `video_list` API response (update the corresponding type in `frontend/src/api/tasks.ts`). In `AssetVideoCard`, only render the "Animate"/"Re-animate" `<Button>` when `item.asset_type === 'ai_video'`; for all other types, render a static label (e.g. "Ken Burns" badge) next to the already-rendered video instead of a button, since Ken-Burns assets are auto-rendered at Step 9 and have no manual re-trigger path.

### Reserve the `/animate` endpoint for `ai_video` assets

In the `POST /runs/{domain}/{run_id}/assets/{scene_id}/{asset_id}/animate` endpoint (`backend/tasks.py:2051-2079`), after resolving `asset_dir`, read `asset_meta.json` and return `400` with a clear message ("Manual animate is only available for ai_video assets") if `asset_type != "ai_video"`, before the existing `animated.txt`-exists check. This keeps the endpoint's existing `animated.txt`-based logic valid (only `ai_video` assets have one) while giving a clear error instead of a confusing "no animation prompt found" message if the frontend gate above is ever bypassed.

## Update tests and documentation

### Remove `Animate`-field tests and add `asset_type`/`intensity` parsing tests in `backend/tests/test_parsers.py`

Delete the now-obsolete `Animate field (duration/split slider feature)` test block (`backend/tests/test_parsers.py:166-245`: `SCENE_PLAN_ANIMATE_PLAIN`/`BOLD` fixtures and their three tests) and the internal-manifest `ANIMATE` field tests (`backend/tests/test_parsers.py:340-384`: `ASSET_MANIFEST_INTERNAL_PLAIN`/`NO_ANIMATE_FIELD` fixtures and their two tests), since `_serialize_scene_plan()` no longer emits an `Animate:` field and `_parse_asset_manifest()` no longer parses one.

Add new tests covering:
- `_parse_asset_manifest()` correctly parses `ken_burns`/`intensity` and omits `animate` from its returned dict.
- `_parse_asset_manifest_scenes()` correctly parses a manifest with `ASSET_TYPE: ai_video` and `KEN_BURNS: N/A` / `INTENSITY: N/A` (both plain and bold-wrapped fixtures, following the existing PLAIN/BOLD pairing convention used throughout this test file).
- A new test module or section for `backend/ken_burns.py`'s `render_ken_burns()` — at minimum a smoke test that it produces a valid output file of the expected duration (using a small test fixture image), following whatever lightweight-media-testing pattern (if any) already exists in the test suite; if none exists, a simple duration/existence check via `Path.exists()` and file size is sufficient given this is pipeline glue code, not pixel-accuracy-critical logic.

### Update `docs/pipeline-overview.md`, `docs/llm-steps.md`, and `docs/asset-generation.md`

- `docs/pipeline-overview.md`: update the Step 8/Step 9 descriptions in the Mermaid diagram and Key Decisions table to reflect the `ai_video`-only scope of Step 8 and the dual-path (AI call vs Ken-Burns render) behavior of Step 9; remove the `Animate` field from the "Resumability"/execution-order narrative if referenced.
- `docs/llm-steps.md`: rewrite the "Step 3 — duration range and the `Animate` field" section (lines 60-70) to describe the new Step 4 mechanism instead — `{{total_duration_seconds}}`/`{{target_ai_video_seconds}}` injection, the `ASSET_TYPE`/`KEN_BURNS`/`INTENSITY` fields, and removal of the `Animate` field from Step 3 and `_parse_beats()`/`_serialize_scene_plan()`.
- `docs/asset-generation.md`: rewrite the Step 8 and Step 9 sections to describe: `asset_meta.json`'s new schema (`asset_type`, nullable `ken_burns`/`intensity` for `ai_video`, `duration`) written at Step 6; Step 8 now only running for `ai_video` and no longer using a Ken-Burns translation table; Step 9's two render paths (`backend/ken_burns.py` for Ken-Burns types, existing OpenRouter/RunPod call for `ai_video`); the per-asset `/animate` endpoint now being `ai_video`-only; and the `video_list` content response's new `asset_type` field.
