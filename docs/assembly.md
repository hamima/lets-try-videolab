# Assembly — Step 17

Step 17 assembles all produced assets, narration, and music into the final video using ffmpeg via `assemble.py`.

## Prerequisites

Steps 14 and 15 must complete before Step 17:

- **Step 14** — `generate_inventory.py` scans `assets/` and writes `asset_inventory.txt`
- **Step 15** — `analyze_timing.py` analyzes `narration.mp3` and writes `narration_timing.json`

Both are called via subprocess with the workspace path passed as `WORKSPACE_DIR`:

```python
result = subprocess.run(
    [sys.executable, str(SCRIPTS_DIR / script_name)],
    cwd=str(BASE_DIR),
    env={**os.environ, "WORKSPACE_DIR": str(ws)},
)
```

## `assemble.py`

Frame-exact ffmpeg assembly (no MoviePy). Exits non-zero on preflight or verification failure.
`--preflight-only` / `--verify-only` are available.

- **Absolute frames:** scene start = `round(start_sec * 30)` from `narration_timing.json`; each scene ends where the next starts. No summed durations, no drift.
- **Narration owns scene length:** long clips are trimmed, short clips hold their last frame; nothing is stretched.
- **Narration untouched:** decoded once, placed at t=0.
- **One sample grid:** 48 kHz, exactly `frames × 1600` samples; music (ducked, looped if short) and sfx placed at frame-derived sample offsets.
- **One encode:** single filter graph, `setpts=N/(30*TB)`, fixed threads, bitexact flags (identical re-renders).
- **Preflight:** missing files, EDL/timing scene-id mismatch, gaps/overlaps, `scene_count`, real `narration.mp3` length vs `total_duration_sec`; warns on every trim/freeze and unknown effect.
- **Verify:** frame count, A/V length (≤1 frame), stream start offsets (<25 ms), audio lag, and first/last frame of every sub-clip must match its own source better than its neighbour.
- Text overlays are rendered to PNGs via `text_overlay.py` (shared with Step 18 below) and composited by ffmpeg.

Accepts the flat-list EDL and the legacy `{project, timeline}` form; tolerates `asset_K` vs `asset_<scene>.K` folder naming.
Tests: `backend/tests/test_assemble.py`.

---

# Subtitles — Step 18 (web app only)

Step 18 only exists in the web app's pipeline (`backend/tasks.py`) — `automate.py`'s CLI pipeline is unchanged and goes straight from Step 17 to Platform Metadata at step 18. See [LLM Steps](llm-steps.md) for the numbering difference.

`scripts/generate_subtitles.py` reads the already-assembled `output/final_video.mp4` plus the narration's timing, and:

1. Builds a list of scene-grouped, timed captions (`backend/subtitles.py`):
   - **Primary path** — if `narration_alignment.json` exists (written by Step 11 when it calls ElevenLabs' `/with-timestamps` endpoint — see [Audio Generation](audio-generation.md)), captions are built from true character-level alignment: grouped into words, packed into line-wrapped, sentence-boundary-preferring chunks (≤2 lines, ≤42 chars/line), then assigned a scene by cross-referencing `narration_timing.json`'s scene windows.
   - **Fallback path** — if no alignment file exists (OpenRouter TTS, or a pre-existing run from before this feature), captions are built per scene from `narration_timing.json`'s existing `internal_pauses` (silence-detected by Step 15) as natural break points, splitting that scene's `[SCENE N]` text from `narration_script.txt` proportionally across them.
   - Either way, every caption's duration is clamped to 1–6 seconds (merging/splitting as needed).
2. Writes `subtitle.md` — a `SCENE N` / `Start:` / `End:` / `Text:` document (`backend/subtitles.py`'s `serialize_subtitles`), editable in the web app via the same viewer/save mechanism as `scene_plan.md`.
3. Burns the captions into `output/final_video.mp4` using a new bottom-center `subtitle` text style (`scripts/text_overlay.py`, shared with Step 17's overlays) — overwriting the video in place. Re-running Step 17 regenerates a clean, caption-free copy if ever needed.

Editing `subtitle.md`'s captions in the UI only rewrites the file — it doesn't automatically re-burn the video, consistent with how every other editable step works (e.g. editing `scene_plan.md` doesn't auto-rerun Step 4). Re-running Step 18, like re-running any other step, recomputes `subtitle.md` from scratch (alignment/timing data) and re-burns — any manual edits made since the last run are discarded, same as re-running Step 1 discards manual edits to `research_dossier.md`.
