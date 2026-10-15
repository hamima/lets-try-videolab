# User-Controlled Video Duration, Video/Image Split, and Cost Estimation

Today the pipeline (`backend/tasks.py`, 18 steps) gives the user zero control over the length or composition of the final video: `GeneratePage.tsx` only collects a `domain` and a fresh/resume toggle. Total video length is an emergent side effect of however many scenes/beats Step 3 (Scene Breakdown) decides to write, and **every** static asset gets animated into a video clip at Step 9 — there is no concept of "some assets stay as images." There is also no cost-estimation infrastructure anywhere in the codebase.

This plan adds three pieces of user control to the "New Run" form on `GeneratePage.tsx`:

1. A **duration range slider** (2-30 min, dual-handle, default 3-6 min) that tells Step 3 the acceptable total-length window, passed straight into its prompt as a constraint (the LLM is free to land anywhere in that window — no post-hoc validation or retries if it doesn't comply, consistent with the pipeline's existing "no special-case failure handling" philosophy).
2. A **video/image split slider** (0-100%, single handle, default 25% video / 75% image, 5% steps) expressing *minutes of animated video* vs *minutes of static Ken-Burns images* in the final cut. This is enforced via a new LLM-driven decision: Step 3 gets a new `Animate: yes/no` field per beat, and the model is told to mark roughly `video_split_percent`% of total narration duration as `Animate: yes`, prioritizing beats with the most visual/motion potential. Step 8 (Animation Prompt) is gated on this flag — assets marked `Animate: no` simply never get an `animated.txt` written, so Step 9's existing batch-animation logic (which already only processes assets *with* `animated.txt`) needs **no changes**.
3. A **live cost estimate**, shown as a dollar range (e.g. "$2.10 – $4.20") below the sliders, computed by a new backend endpoint using a simple blended-rate formula calibrated against real OpenRouter pricing (queried live during planning — see Task 2 for exact figures). The estimate recomputes (debounced) whenever either slider moves.

Key decisions carried through every task below:
- The existing domain dropdown is treated as "choosing the topic" — no new topic text field is added.
- `duration_min_minutes` / `duration_max_minutes` / `video_split_percent` are transported via a new nested `video_config` object on `StartRunRequest`, and persisted into the existing per-run `state` dict (same place `voice_id` already lives) — no new config files.
- No slider UI component exists in the frontend today (`frontend/src/components/ui/` is a shadcn/Radix-based set with no `Slider`). A new `@radix-ui/react-slider` dependency and `components/ui/slider.tsx` are required.
- Cost estimation is inherently approximate (true token counts aren't knowable pre-generation) — the formula should document its unit-cost assumptions inline as code comments, in the same style as the existing `backend/open_router/models.py` pricing comments.

## Build the slider UI primitive and wire the new run-config controls into GeneratePage

Add the missing Radix-based slider component and use it to build the two new controls on the existing "New Run" form, with all three new UI elements (duration slider, split slider, cost estimate) visible at once with sensible defaults applied — no progressive disclosure/reveal-on-interact logic needed.

### Add a Slider primitive to `frontend/src/components/ui/`

Install `@radix-ui/react-slider` (matching the existing pattern of thin wrappers around Radix primitives already used for dialog/select/progress/etc. in this folder) and create `frontend/src/components/ui/slider.tsx` following the existing styling conventions (Tailwind + CVA) seen in `button.tsx`/`progress.tsx`. Must support:
- Dual-handle (range) mode for the duration slider.
- Single-handle mode for the split slider.
- A `step` prop for snapping (whole minutes for duration, 5% increments for split).

### Build the duration range slider

In `GeneratePage.tsx`, add a dual-handle range slider bound to local state `[durationMin, durationMax]`, spanning 2-30 minutes, defaulting to `[3, 6]`, snapping to whole-minute steps. Display the current selected range as text (e.g. "3 – 6 min") near the slider.

### Build the video/image split slider

Add a single-handle slider bound to local state `videoSplitPercent`, spanning 0-100%, defaulting to `25`, snapping to 5% increments. Label it clearly as "% of final video that is animated" with the remainder implicitly "% static images" (e.g. "25% video / 75% image").

### Wire defaults and local state

Both sliders' state should live alongside the existing `domain`/`fresh` state in `GeneratePage.tsx`, initialized to the defaults above on mount, and passed into the `startRun()` API call (see Task 3) and into the cost-estimate hook (see Task 2) whenever either value changes.

## Add backend cost estimation and surface it live in the UI

### Build the cost-estimate pricing model and endpoint

Create `backend/cost_estimate.py` (new module, following the same "plain constants + a small pure function" style as `backend/open_router/models.py`) implementing a blended-rate formula:

```
total_cost = flat_overhead + narration_rate * total_minutes + video_rate * video_minutes + image_rate * image_minutes
```

Where `video_minutes = total_minutes * (video_split_percent / 100)` and `image_minutes = total_minutes * (1 - video_split_percent / 100)`.

Calibrate the per-unit rates from real OpenRouter pricing (confirmed live against `GET /api/v1/models` and `GET /api/v1/videos/models` during planning — re-verify at implementation time in case prices have moved):
- **Video** (`alibaba/wan-2.6`, image-to-video, 720p — matches the resolution default already set in `backend/open_router/models.py`): **$0.10 per second** → $6.00/min.
- **Text models** (`google/gemini-2.5-pro`): prompt $1.25/M tokens, completion $10/M tokens. Used for the flat overhead (research, story script, scene breakdown, asset manifest/acquisition, music prompt, platform metadata — these steps scale weakly with duration; treat as a fixed per-run estimate based on typical token counts for a single run).
- **Image** (`google/gemini-3.1-flash-image`): prompt $0.50/M tokens, completion $3/M tokens, plus a per-image output cost (`image_output: $0.00006` per output-image-token — document the assumed tokens-per-image conversion inline as a comment, since OpenRouter doesn't publish a direct "$ per image" figure for this model).
- **Narration TTS** (`google/gemini-3.1-flash-tts-preview`): prompt $1/M tokens, completion (audio) $20/M tokens — scale with `total_minutes` assuming ~150 words/min narration pace; document the words-to-tokens and audio-token-rate assumptions inline.
- **Music** (`google/lyria-3-clip-preview`): flat **$0.04 per run** (fixed ~30s clip regardless of requested duration, per the existing `generate_music()` behavior where `duration_seconds` is accepted but unused) — fold into `flat_overhead`.

Expose this via `GET /tasks/estimate-cost?duration_min=<int>&duration_max=<int>&video_split=<int>` in `backend/tasks.py` (matches the existing read-only `@router.get` convention used elsewhere, e.g. `GET /runs/{domain}/{run_id}`). Compute the cost twice — once at `duration_min` and once at `duration_max` — and return `{"min_cost": ..., "max_cost": ...}` so the range slider directly produces a cost range.

### Wire the frontend cost display

Add a function to `frontend/src/api/tasks.ts` calling the new endpoint, and call it from `GeneratePage.tsx` (debounced ~300-500ms) whenever `durationMin`, `durationMax`, or `videoSplitPercent` changes. Display the returned `{min_cost, max_cost}` as a formatted dollar range (e.g. "Estimated cost: $2.10 – $4.20") directly below the split slider. Show a loading/skeleton state during the debounced fetch using the existing `skeleton.tsx` component.

## Carry duration/split config from the frontend through to a new run's persisted state

### Extend `StartRunRequest` and the `/tasks/runs` call site

In `backend/tasks.py`, add a nested `VideoConfig` model to `StartRunRequest`:

```python
class VideoConfig(BaseModel):
    duration_min_minutes: int
    duration_max_minutes: int
    video_split_percent: int

class StartRunRequest(BaseModel):
    domain: str
    fresh: bool = False
    preview_only: bool = False
    video_config: Optional[VideoConfig] = None
```

Update `frontend/src/api/tasks.ts`'s `startRun()` signature and its call site in `GeneratePage.tsx` to pass `{domain, fresh, preview_only, video_config: {duration_min_minutes, duration_max_minutes, video_split_percent}}`. Basic validation (`duration_min_minutes <= duration_max_minutes`, both within 2-30, `video_split_percent` within 0-100) can happen client-side via the slider bounds themselves — no additional server-side validation needed given the existing codebase's light-validation style.

### Persist `video_config` into run state

In `start_run()`'s fresh-start branch (`backend/tasks.py`), add `video_config` (as a plain dict) alongside the existing `completed`/`failed`/`domain`/`voice_id` keys in the `state` dict before `save_state(ws, state)`. On resume (non-fresh), the previously-persisted `video_config` is simply read back via `load_state(ws)` as-is — no new logic needed there.

## Extend Step 3 (Scene Breakdown) to plan within the duration range and assign the Animate flag

### Inject duration range and split budget into all 8 domain prompt files

Each of `prompts/{domain}/03_scene_breakdown.md` (political, general_knowledge, science, business, history, sports, technology, general) needs two additions:
- A new instruction referencing `{{duration_range}}` (e.g. rendered as "Plan a total video length between 3 and 6 minutes") injected the same way `{{story_script}}` already is, per the mechanism described in `docs/llm-steps.md`.
- A new instruction referencing `{{video_split_percent}}` telling the model to mark approximately that percentage of total narration duration as `Animate: yes` (prioritizing beats with strong visual/motion potential) and the rest as `Animate: no`.
- A new `Animate:` field added to the per-scene output format block (alongside the existing `Narration:`/`Duration:`/`Purpose:`/`Emotion:` fields), e.g.:
  ```
  Animate:
  yes
  ```

Update the prompt-loading/templating logic (wherever `{{story_script}}` substitution currently happens for Step 3) to also substitute `{{duration_range}}` and `{{video_split_percent}}` from `state["video_config"]`.

### Update scene-plan parsing/serialization for the new `Animate` field

In `backend/tasks.py`:
- `_parse_beats` must parse the new `Animate:` label (handling both plain and `**Animate:**` bold-label formats, matching the existing dual-format support for `Narration`/`Duration`/`Purpose`/`Emotion`).
- `_serialize_scene_plan` must emit the `Animate:` field when re-serializing beats (used when a scene plan is edited/saved via the UI).
- Propagate the flag from Step 3's scene plan into Step 4's asset manifest (`_parse_asset_manifest_scenes`/asset-planning prompt) so each generated asset carries its `animate` decision through to Step 8.

### Add test coverage for the `Animate` field

Extend `backend/tests/test_parsers.py` with new fixtures/assertions mirroring the existing `SCENE_PLAN_PLAIN`/`SCENE_PLAN_BOLD` pattern, covering:
- `Animate: yes` / `Animate: no` in plain-text format.
- `**Animate:**` in bold-label format.
- Confirm `_serialize_scene_plan` round-trips the field correctly.

## Gate Step 8's animation-prompt generation on the Animate flag and update docs

### Skip `animated.txt` generation for `Animate: no` assets

In Step 8's per-asset animation-prompt logic (`_run_animation_prompt_step` in `backend/tasks.py`), check the asset's `animate` flag (threaded through from Step 3/4 per Task 4) before generating `animated.txt`. If `animate` is `no`, skip the Gemini/OpenRouter call entirely and leave the asset without an `animated.txt` file — Step 9's existing batch runner already only animates assets that have one, so **no changes to Step 9 are needed**.

### Update documentation

- `docs/pipeline-overview.md`: note that total video duration and video/image composition are now user-configurable inputs (not purely emergent), referencing the new `video_config`.
- `docs/llm-steps.md`: add `{{duration_range}}` and `{{video_split_percent}}` to Step 3's "Variables injected" table row, and document the new `Animate` field.
- `docs/asset-generation.md`: update the Step 8 section to describe the new animate/skip gating logic, and clarify that "not every static asset is animated anymore" (superseding the current "only static assets are animated" framing, which previously implied *all* of them were).
