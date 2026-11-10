# Pipeline Overview

## Flow Diagram

```mermaid
flowchart TD
    USER([fa:fa-user User]) --> CMD{Command}

    CMD -->|python automate.py| FULL[Full Run]
    CMD -->|python automate.py --new| FULL_NEW[Full Run — fresh]
    CMD -->|"python automate.py --step N --workspace id"| SINGLE_WS[Single Step]
    CMD -->|"python automate.py --step N --workspace id --new"| SINGLE_FORCE[Single Step — force re-run]
    CMD -->|python automate.py --step 1 --new| SINGLE_NEW[Single Step — new workspace]
    CMD -->|"python automate.py --status --workspace id"| STATUS[Show Status]

    FULL --> MENU_FULL["🎬 Select Domain\npolitical / science / business\nhistory / sports / technology\ngeneral_knowledge / general"]
    FULL_NEW --> MENU_FULL
    SINGLE_WS --> MENU_STEP["🎬 Select Domain"]
    SINGLE_FORCE --> MENU_STEP
    SINGLE_NEW --> MENU_STEP
    STATUS --> MENU_STATUS["🎬 Select Domain"]

    MENU_FULL --> VOICE["Set ElevenLabs voice ID\nfrom DOMAIN_VOICE_MAP"]
    VOICE --> RESUME{--new flag?}
    RESUME -->|yes| WS_NEW["Create workspace/{domain}/YYYY-MM-DD_HHMMSS/"]
    RESUME -->|no| RESUME2{Latest workspace\nexists for domain?}
    RESUME2 -->|yes| WS_RESUME["Resume workspace/{domain}/latest/"]
    RESUME2 -->|no| WS_NEW

    MENU_STEP --> STEP_NEW{"--new, no --workspace?"}
    STEP_NEW -->|yes| WS_NEW
    STEP_NEW -->|no| WS_FIND["find_workspace(domain, id)\nworkspace/{domain}/YYYY-MM-DD_id/"]
    WS_FIND --> OUTPUT_CHECK{Output already exists?}
    OUTPUT_CHECK -->|yes, no --new| SKIP[Skip step]
    OUTPUT_CHECK -->|no, or --new| RUN_STEP[Run step]

    MENU_STATUS --> WS_STATUS_FIND["find_workspace(domain, id)"]
    WS_STATUS_FIND --> WS_STATUS(["Print step table\nand exit"])

    WS_RESUME --> S1
    WS_NEW --> S1

    subgraph PROMPTS ["📁 Domain Prompt Files"]
        PF["prompts/{domain}/\n01_research · 02_story · 03_scene_breakdown\n04_asset_planning · 05_asset_acquisition\n08_animation_prompt · 10_narration · 12_music\n16_creative_director · 02b_platform_metadata"]
    end

    subgraph LLM ["🤖 Gemini 2.5 Pro — LLM Steps (fallback: 2.0 Flash)"]
        S1["Step 1 · Research\nresearch_dossier.md"]
        S2["Step 2 · Story Script\nstory_script.md"]
        S3["Step 3 · Scene Breakdown\nscene_plan.md"]
        S4["Step 4 · Asset Manifest\nasset_manifest.md"]
        S5["Step 5 · Acquisition Instructions\nasset_acquisition.md"]
        S1 --> S2 --> S3 --> S4 --> S5
    end

    PF -.->|load prompt for domain| S1
    PF -.->|load prompt for domain| S2
    PF -.->|load prompt for domain| S3
    PF -.->|load prompt for domain| S4
    PF -.->|load prompt for domain| S5

    subgraph ASSETS ["📦 Asset Track (Steps 6–9)"]
        S6["Step 6 · Write Asset Files\nai_video / ai_image → generated.txt\n+ asset_meta.json per asset (asset_type, ken_burns, intensity, duration)"]
        S7["Step 7 · Image Acquisition\ngenerated.txt → Imagen 4 → image.png"]
        S8["Step 8 · Animation Prompt\nai_video assets only\nGemini → animated.txt"]
        S9["Step 9 · Video Animation\nai_video → OpenRouter/RunPod → animated.mp4\nai_image → backend/ken_burns.py (Python render) → animated.mp4"]
        S6 --> S7 --> S8 --> S9
    end

    subgraph NARRATION ["🎙️ Narration Track (Steps 10–11)"]
        S10["Step 10 · Gemini\nNarration Script\nnarration_script.txt"]
        S11["Step 11 · ElevenLabs v3 TTS\nnarration.mp3"]
        S10 --> S11
    end

    subgraph MUSIC ["🎵 Music Track (Steps 12–13)"]
        S12["Step 12 · Gemini\nMusic Prompt\nmusic_prompt.txt"]
        S13["Step 13 · ElevenLabs v3 Music Gen\n22s clip → ffmpeg loop → 210s music.wav"]
        S12 --> S13
    end

    subgraph ASSEMBLE ["🎬 Assembly & Publish (Steps 14–18)"]
        S14["Step 14 · Asset Inventory\nasset_inventory.txt"]
        S15["Step 15 · Narration Timing\nnarration_timing.json"]
        S16["Step 16 · Gemini\nEdit Decision List\nedl.json"]
        S17["Step 17 · Final Assembly\nassemble.py → final_video.mp4"]
        S18["Step 18 · Platform Metadata\nGemini → platform_metadata.json\nYouTube title · description · hashtags · tags"]
        S14 --> S15 --> S16 --> S17 --> S18
    end

    PF -.->|load prompt for domain| S8
    PF -.->|load prompt for domain| S10
    PF -.->|load prompt for domain| S12
    PF -.->|load prompt for domain| S16
    PF -.->|load prompt for domain| S18

    S5 --> S6
    S2 --> S10
    S3 --> S12

    S9 --> S14
    S11 --> S14
    S13 --> S14

    S18 --> OUT([output/final_video.mp4\nplatform_metadata.json])

    subgraph STATE ["📋 State Management"]
        STATEFILE["pipeline_state.json\ncompleted / failed / domain / voice_id"]
    end

    WS_NEW -.->|write domain + voice| STATEFILE
    STATEFILE -.->|skip if done| S2
    STATEFILE -.->|skip if done| S3
    STATEFILE -.->|skip if done| S4
```

## Goals

Replace all manual steps in `pipeline.py` with a single automated script `automate.py`. The script calls Gemini 2.5 Pro for all LLM and creative tasks, ElevenLabs v3 for narration and music, Imagen 4 for AI image generation, and RunPod (LTX-Video) for video animation. Steps 14, 15, and 17 call external scripts via subprocess.

Total video duration and video/image composition are **user-configurable inputs**, not a purely emergent side effect of Step 3's scene count. `GeneratePage.tsx`'s duration-range and video/image-split sliders are sent as a `video_config` object (`duration_min_minutes`, `duration_max_minutes`, `video_split_percent`) on `POST /tasks/runs`, persisted into the run's `pipeline_state.json`, and injected into Step 3's and Step 4's prompts — see `docs/llm-steps.md`. `video_split_percent` controls what fraction of total narration time is assigned to `ai_video` (AI-animated) assets at Step 4; everything else is `ai_image`, rendered with Python zoom/pan (Ken Burns) rather than an AI video call.

## Key Decisions

| Concern | Decision |
|---------|----------|
| LLM | `gemini-2.5-pro`; falls back to `gemini-2.0-flash` on 429 quota errors |
| Image gen | Imagen 4 (`imagen-4.0-generate-001`) for `ai_video` / `ai_image` assets (step 7) |
| Asset types | `ai_video`, `ai_image` — defined in step 5 prompt. `ai_video` is animated by an AI video model from a free-form motion prompt; `ai_image` is animated in Python via Ken Burns zoom/pan (`backend/ken_burns.py`) |
| Step 6 | Writes `generated.txt` plus `asset_meta.json` for every asset — no network calls |
| Step 7 | Imagen pass only: `generated.txt` → `image.png` |
| Step 8 | `ai_video`-only — generates `animated.txt` (motion prompt) for each `ai_video` asset; `ai_image` assets skip step 8 entirely since their motion is already fully specified by `asset_meta.json`'s `ken_burns`/`intensity` fields |
| Step 9 | Branches per asset by `asset_meta.json`'s `asset_type`: `ai_video` → OpenRouter/RunPod AI animation; `ai_image` → `backend/ken_burns.py`'s `render_ken_burns()`, a pure-Python MoviePy zoom/pan render |
| TTS & Music | ElevenLabs model v3 |
| Voice | Domain chosen upfront → maps to `DOMAIN_VOICE_MAP` |
| Domains | Interactive menu at startup: `political`, `general_knowledge`, `science`, `business`, `history`, `sports`, `technology`, `general` |
| Prompts | Domain-specific files under `prompts/{domain}/` |
| Workspace | Scoped per domain — `workspace/{domain}/YYYY-MM-DD_HHMMSS/`; each run gets its own folder, previous workspaces are never overwritten |
| Resumability | `pipeline_state.json` tracks completed steps and domain; default full run resumes latest workspace |
| `--step` / `--status` | Both require `--workspace <id>`; `--step` skips if output exists unless `--new` is also passed. **Exception: step 7 always runs (per-asset check)** |
| `--new` | With `--step --workspace`: force re-runs the step. With `--step 7`: deletes all existing images then regenerates all. With `--step 1` only: creates a fresh workspace |
| `--workspace <id>` | Targets a specific workspace by time ID (e.g. `200619` from `2026-06-12_200619`) |
| Platform metadata | Step 18 — runs last after final assembly; Gemini generates YouTube title/description/hashtags/tags from research + story |
| Video animation | RunPod pod running LTX-Video I2V server (`runpod/server.py`) on port 8080 |
| Assembly | ffmpeg via `assemble.py` (step 17) driven by `edl.json` |
| API keys | Loaded from `.keys` via `source .keys` before running |

## Execution Order

```
1   → run_gemini_step()           # research_dossier.md
2   → run_gemini_step()           # story_script.md
3   → run_gemini_step()           # scene_plan.md
4   → run_gemini_step()           # asset_manifest.md
5   → run_gemini_step()           # asset_acquisition.md
6   → run_fetch_assets()          # generated.txt
7   → run_imagen_generation()     # generated.txt → image.png (Imagen 4)
8   → run_animation_prompt_step() # animated.txt per ai_video asset only (Gemini, uses 08_animation_prompt.md)
9   → run_runpod_animation()      # animated.mp4 per asset — ai_video via OpenRouter/RunPod,
                                  # ai_image via backend/ken_burns.py (Python zoom/pan)
10  → run_gemini_step()           # narration_script.txt  [uses 10_narration.md]
11  → run_elevenlabs_tts()        # narration.mp3
12  → run_gemini_step()           # music_prompt.txt  [uses 12_music.md]
13  → run_elevenlabs_music()      # music.wav (22s clip → looped to 210s via ffmpeg)
14  → run_script()                # asset_inventory.txt
15  → run_script()                # narration_timing.json
16  → run_gemini_step()           # edl.json  [uses 16_creative_director.md]
17  → run_script()                # output/final_video.mp4 (assemble.py)
18  → run_gemini_step()           # platform_metadata.json  [uses 02b_platform_metadata.md]
```
