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

Accepts the flat-list EDL and the legacy `{project, timeline}` form; tolerates `asset_K` vs `asset_<scene>.K` folder naming.
Tests: `backend/tests/test_assemble.py`.
