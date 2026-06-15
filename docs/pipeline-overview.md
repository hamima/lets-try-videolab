# Pipeline Overview

## Flow Diagram

```mermaid
flowchart TD
    USER([fa:fa-user User]) --> CMD{Command}

    CMD -->|"python automate.py [--assembler X]"| FULL[Full Run]
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
        PF["prompts/{domain}/\n01_research · 02_story · 02b_platform_metadata\n03_scene_breakdown · 04_asset_planning · 05_asset_acquisition\n08_narration · 10_music · 13_creative_director"]
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

    subgraph ASSETS ["📦 Asset Track (Steps 6–7)"]
        S6["Step 6 · Fetch Assets (built-in)\nai_video → generated.txt\nmap → map_spec.json\nchart → chart_spec.json\nstock → Pexels download"]
        S7A["Step 7a · Imagen 4\nai_video assets → image.png"]
        S7B["Step 7b · Map Renderer\nFolium → PNG\n± FLUX.1 img2img style"]
        S7C["Step 7c · Chart Renderer\nmatplotlib → PNG\n± FLUX.1 img2img style"]
        S6 --> S7A
        S6 --> S7B
        S6 --> S7C
    end

    subgraph NARRATION ["🎙️ Narration Track (Steps 8–9)"]
        S8["Step 8 · Gemini\nNarration Script\nnarration_script.txt"]
        S9["Step 9 · ElevenLabs v3 TTS\nnarration.mp3"]
        S8 --> S9
    end

    subgraph MUSIC ["🎵 Music Track (Steps 10–11)"]
        S10["Step 10 · Gemini\nMusic Prompt\nmusic_prompt.txt"]
        S11["Step 11 · ElevenLabs v3 Music Gen\n22s clip → ffmpeg loop → 210s music.wav"]
        S10 --> S11
    end

    subgraph ASSEMBLE ["🎬 Assembly (Steps 12–14)"]
        S12["Step 12 · Asset Inventory\nasset_inventory.txt"]
        S12B["Step 12b · Narration Timing\nnarration_timing.json"]
        S13["Step 13 · Gemini\nEdit Decision List\nedl.json"]
        S14_CHOICE{--assembler?}
        S14_FFMPEG["Step 14 · ffmpeg\nassemble.py\nEDL-driven"]
        S14_REP["Step 14 · Replicate\nEDL mode: SVD img→video\nCreative mode: CogVideoX"]
        S14_RUN["Step 14 · RunPod\nEDL mode: SVD img→video\nCreative mode: Wan2.1-14B"]
        S12 --> S12B --> S13 --> S14_CHOICE
        S14_CHOICE -->|ffmpeg| S14_FFMPEG
        S14_CHOICE -->|replicate| S14_REP
        S14_CHOICE -->|runpod| S14_RUN
    end

    PF -.->|load prompt for domain| S8
    PF -.->|load prompt for domain| S10
    PF -.->|load prompt for domain| S13

    S5 --> S6
    S2 --> S8
    S3 --> S10

    S7A --> S12
    S7B --> S12
    S7C --> S12
    S9 --> S12
    S11 --> S12

    S14_FFMPEG --> OUT([output/final_video.mp4])
    S14_REP --> OUT
    S14_RUN --> OUT

    subgraph STATE ["📋 State Management"]
        STATEFILE["pipeline_state.json\ncompleted / failed / domain / voice_id / assembler"]
    end

    WS_NEW -.->|write domain + voice + assembler| STATEFILE
    STATEFILE -.->|skip if done| S2
    STATEFILE -.->|skip if done| S3
    STATEFILE -.->|skip if done| S4
```

## Goals

Replace all manual steps in `pipeline.py` with a single automated script `automate.py`. The script calls Gemini 2.5 Pro for all LLM and creative tasks, ElevenLabs v3 for narration and music, and Imagen 4 for AI image generation. Steps 12, 12b, and 14 call external scripts via subprocess (ffmpeg mode) or assembler modules (replicate/runpod modes).

## Key Decisions

| Concern | Decision |
|---------|----------|
| LLM | `gemini-2.5-pro`; falls back to `gemini-2.0-flash` on 429 quota errors |
| Image gen | Imagen 4 (`imagen-4.0-generate-001`) for `ai_video` assets (step 7a) |
| Map gen | Folium → headless Playwright screenshot → optional FLUX.1 img2img style (step 7b) |
| Chart gen | matplotlib → PNG → optional FLUX.1 img2img style (step 7c) |
| TTS & Music | ElevenLabs model v3 |
| Voice | Domain chosen upfront → maps to `DOMAIN_VOICE_MAP` |
| Domains | Interactive menu at startup: `political`, `general_knowledge`, `science`, `business`, `history`, `sports`, `technology` |
| Prompts | Domain-specific files under `prompts/{domain}/` |
| Workspace | Scoped per domain — `workspace/{domain}/YYYY-MM-DD_HHMMSS/`; latest auto-resumed |
| Resumability | `pipeline_state.json` tracks completed steps, domain, assembler |
| Platform metadata | Step 2b — Gemini generates YouTube title/description/hashtags/tags; stored in `platform_metadata.json` with a `youtube` key (IG/TikTok added later) |
| Assembler | `--assembler ffmpeg` (default) \| `replicate` \| `runpod`; each supports EDL-driven and creative modes |
| API keys | Loaded from `.keys` via `source .keys` before running |

## Execution Order

```
1   → run_gemini_step()       # research_dossier.md
2   → run_gemini_step()       # story_script.md
2b  → run_gemini_step()       # platform_metadata.json (YouTube title, description, hashtags, tags)
3   → run_gemini_step()       # scene_plan.md
4   → run_gemini_step()       # asset_manifest.md
5   → run_gemini_step()       # asset_acquisition.md
6   → run_fetch_assets()      # generated.txt / map_spec.json / chart_spec.json / Pexels downloads
7a  → run_imagen_generation() # image.png per ai_video asset
7b  → run_map_generation()    # map.png per map asset (Folium + optional FLUX.1)
7c  → run_chart_generation()  # chart.png per chart asset (matplotlib + optional FLUX.1)
8   → run_gemini_step()       # narration_script.txt
9   → run_elevenlabs_tts()    # narration.mp3
10  → run_gemini_step()       # music_prompt.txt
11  → run_elevenlabs_music()  # music.wav (22s clip → looped to 210s via ffmpeg)
12  → run_script()            # asset_inventory.txt
12b → run_script()            # narration_timing.json
13  → run_gemini_step()       # edl.json
14  → run_assembler()         # output/final_video.mp4
```
