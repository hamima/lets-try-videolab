# Pipeline Overview

## Flow Diagram

```mermaid
flowchart TD
    USER([fa:fa-user User]) --> CMD{Command}

    CMD -->|python automate.py| FULL[Full Run]
    CMD -->|python automate.py --step N| SINGLE[Single Step]
    CMD -->|python automate.py --status| STATUS[Show Status]

    FULL --> MENU_FULL["🎬 Select Domain\npolitical / science / business\nhistory / sports / technology\ngeneral_knowledge"]
    SINGLE --> MENU_STEP["🎬 Select Domain"]
    STATUS --> MENU_STATUS["🎬 Select Domain"]

    MENU_FULL --> VOICE["Set ElevenLabs voice ID\nfrom DOMAIN_VOICE_MAP"]
    VOICE --> RESUME{Latest workspace\nexists for domain?}
    RESUME -->|yes| WS_RESUME["Resume workspace/{domain}/latest/"]
    RESUME -->|no| WS_NEW["Create workspace/{domain}/YYYY-MM-DD_HHMMSS/"]

    MENU_STEP --> WS_LATEST["Detect latest workspace/{domain}/\nRun requested step only"]
    MENU_STATUS --> WS_STATUS(["Print step table\nand exit"])

    WS_RESUME --> S1
    WS_NEW --> S1

    subgraph PROMPTS ["📁 Domain Prompt Files"]
        PF["prompts/{domain}/\n01_research · 02_story · 02b_platform_metadata\n03_scene_breakdown · 04_asset_planning · 05_asset_acquisition\n08_animation_prompt · 10_narration · 12_music · 16_creative_director"]
    end

    subgraph LLM ["🤖 Gemini 2.5 Pro — LLM Steps (fallback: 2.0 Flash)"]
        S1["Step 1 · Research\nresearch_dossier.md"]
        S2["Step 2 · Story Script\nstory_script.md"]
        S2B["Step 2b · Platform Metadata\nplatform_metadata.json\nYouTube title · description · hashtags · tags"]
        S3["Step 3 · Scene Breakdown\nscene_plan.md"]
        S4["Step 4 · Asset Manifest\nasset_manifest.md"]
        S5["Step 5 · Acquisition Instructions\nasset_acquisition.md"]
        S1 --> S2 --> S2B
        S2 --> S3 --> S4 --> S5
    end

    PF -.->|load prompt for domain| S1
    PF -.->|load prompt for domain| S2
    PF -.->|load prompt for domain| S2B
    PF -.->|load prompt for domain| S3
    PF -.->|load prompt for domain| S4
    PF -.->|load prompt for domain| S5

    subgraph ASSETS ["📦 Asset Track (Steps 6–9)"]
        S6["Step 6 · Fetch Assets (built-in)\nai_video → generated.txt\nmap → map_spec.json\nchart → chart_spec.json\nstock → Pexels download"]
        S7A["Step 7a · Imagen 4\nai_video assets → image.png"]
        S7B["Step 7b · Map Renderer\nFolium → PNG"]
        S7C["Step 7c · Chart Renderer\nmatplotlib → PNG"]
        S8["Step 8 · Animation Prompt\nGemini → animated.txt per static asset"]
        S9["Step 9 · RunPod Animation\nWan2.1 → animated.mp4 per static asset"]
        S6 --> S7A
        S6 --> S7B
        S6 --> S7C
        S7A --> S8
        S7B --> S8
        S7C --> S8
        S8 --> S9
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

    subgraph ASSEMBLE ["🎬 Assembly (Steps 14–17)"]
        S14["Step 14 · Asset Inventory\nasset_inventory.txt"]
        S15["Step 15 · Narration Timing\nnarration_timing.json"]
        S16["Step 16 · Gemini\nEdit Decision List\nedl.json"]
        S17["Step 17 · Final Assembly\nassemble.py → final_video.mp4"]
        S14 --> S15 --> S16 --> S17
    end

    PF -.->|load prompt for domain| S8
    PF -.->|load prompt for domain| S10
    PF -.->|load prompt for domain| S12
    PF -.->|load prompt for domain| S16

    S5 --> S6
    S2 --> S10
    S3 --> S12

    S9 --> S14
    S11 --> S14
    S13 --> S14

    S17 --> OUT([output/final_video.mp4])

    subgraph STATE ["📋 State Management"]
        STATEFILE["pipeline_state.json\ncompleted / failed / domain / voice_id"]
    end

    WS_NEW -.->|write domain + voice| STATEFILE
    STATEFILE -.->|skip if done| S2
    STATEFILE -.->|skip if done| S3
    STATEFILE -.->|skip if done| S4
```

## Goals

Replace all manual steps in `pipeline.py` with a single automated script `automate.py`. The script calls Gemini 2.5 Pro for all LLM and creative tasks, ElevenLabs v3 for narration and music, Imagen 4 for AI image generation, and RunPod for video animation. Steps 14, 15, and 17 call external scripts via subprocess.

## Key Decisions

| Concern | Decision |
|---------|----------|
| LLM | `gemini-2.5-pro`; falls back to `gemini-2.0-flash` on 429 quota errors |
| Image gen | Imagen 4 (`imagen-4.0-generate-001`) for `ai_video` assets (step 7a) |
| Map gen | Folium → headless Playwright screenshot (step 7b) |
| Chart gen | matplotlib → PNG (step 7c) |
| TTS & Music | ElevenLabs model v3 |
| Voice | Domain chosen upfront → maps to `DOMAIN_VOICE_MAP` |
| Domains | Interactive menu at startup: `political`, `general_knowledge`, `science`, `business`, `history`, `sports`, `technology` |
| Prompts | Domain-specific files under `prompts/{domain}/` |
| Workspace | Scoped per domain — `workspace/{domain}/YYYY-MM-DD_HHMMSS/`; latest auto-resumed |
| Resumability | `pipeline_state.json` tracks completed steps and domain |
| Platform metadata | Step 2b — Gemini generates YouTube title/description/hashtags/tags; stored in `platform_metadata.json` with a `youtube` key (IG/TikTok added later) |
| Video animation | RunPod serverless (Wan2.1) — `RUNPOD_ENDPOINT` is a placeholder; set before running step 9 |
| Assembly | ffmpeg via `assemble.py` (step 17) driven by `edl.json` |
| API keys | Loaded from `.keys` via `source .keys` before running |

## Execution Order

```
1   → run_gemini_step()           # research_dossier.md
2   → run_gemini_step()           # story_script.md
2b  → run_gemini_step()           # platform_metadata.json (YouTube title, description, hashtags, tags)
3   → run_gemini_step()           # scene_plan.md
4   → run_gemini_step()           # asset_manifest.md
5   → run_gemini_step()           # asset_acquisition.md
6   → run_fetch_assets()          # generated.txt / map_spec.json / chart_spec.json / Pexels downloads
7a  → run_imagen_generation()     # image.png per ai_video asset
7b  → run_map_generation()        # map.png per map asset (Folium)
7c  → run_chart_generation()      # chart.png per chart asset (matplotlib)
8   → run_animation_prompt_step() # animated.txt per static asset (Gemini)
9   → run_runpod_animation()      # animated.mp4 per static asset (RunPod — placeholder config)
10  → run_gemini_step()           # narration_script.txt  [uses 08_narration.md]
11  → run_elevenlabs_tts()        # narration.mp3
12  → run_gemini_step()           # music_prompt.txt  [uses 10_music.md]
13  → run_elevenlabs_music()      # music.wav (22s clip → looped to 210s via ffmpeg)
14  → run_script()                # asset_inventory.txt
15  → run_script()                # narration_timing.json
16  → run_gemini_step()           # edl.json  [uses 13_creative_director.md]
17  → run_script()                # output/final_video.mp4 (assemble.py)
```
