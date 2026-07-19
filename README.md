# VidLife

Automated documentary video pipeline. Given a domain and topic, the pipeline researches, scripts, sources assets, generates narration and music, and assembles a final video — end to end with a single command.

## Quick Start

```bash
# 1. Install dependencies
pip install google-genai requests moviepy folium playwright matplotlib
playwright install chromium
brew install ffmpeg

# 2. Set API keys
source .keys   # copy .keys from template and fill in your values

# 3. Run
python automate.py
```

The pipeline prompts you to select a domain, then runs all steps automatically. It resumes from the last completed step if you re-run it.

## CLI

```bash
python automate.py                                      # full run — resumes latest workspace
python automate.py --new                                # full run — always starts a fresh workspace
python automate.py --step 3 --workspace 200619          # run step 3 (skip if already done)
python automate.py --step 3 --workspace 200619 --new    # force re-run step 3
python automate.py --step 1 --new                       # start a brand-new workspace and run step 1
python automate.py --status --workspace 200619          # show step status table for a workspace
```

- `--workspace` is **required** with `--step` and `--status` (use the time portion of the folder name, e.g. `200619` from `2026-06-12_200619`)
- `--step` skips the step if its output already exists — pass `--new` to force re-run
- `--step 1 --new` (no `--workspace`) creates a fresh workspace

## Domains

`political` · `general_knowledge` · `science` · `business` · `history` · `sports` · `technology` · `general`

Each domain has its own prompt files under `prompts/{domain}/` and a dedicated ElevenLabs voice.

## API Keys

Copy `.keys`, fill in your values, and `source .keys` before each session:

| Key | Service |
|-----|---------|
| `GEMINI_API_KEY` | Google AI Studio / Vertex AI |
| `ELEVENLABS_API_KEY` | ElevenLabs |
| `PEXELS_API_KEY` | Pexels |
| `PIXABAY_API_KEY` | Pixabay |
| `RUNPOD_API_KEY` | RunPod (step 9 — video animation) |

Also set `RUNPOD_ENDPOINT` and `RUNPOD_MODEL` in `automate.py` before running step 9.

## Documentation

| Doc | Contents |
|-----|----------|
| [Pipeline Overview](docs/pipeline-overview.md) | Full flow diagram, key decisions, execution order |
| [Scaffolding](docs/scaffolding.md) | CLI args, workspace layout, state file, domain/voice config |
| [LLM Steps](docs/llm-steps.md) | Gemini runner, text-generation steps (1–5, 8, 10, 12, 16, 18) |
| [Asset Generation](docs/asset-generation.md) | Steps 6–9: fetch, Imagen 4, maps, charts, animation prompts, RunPod |
| [Audio Generation](docs/audio-generation.md) | Step 11 ElevenLabs TTS, Step 13 music generation |
| [Assembly](docs/assembly.md) | Step 17 — ffmpeg assembly via `assemble.py`; Step 18 — platform metadata |

## Project Structure

```
automate.py              # main pipeline script
pipeline.py              # original manual pipeline (reference)
prompts/
  {domain}/
    01_research.md
    02_story.md
    02b_platform_metadata.md   # step 18 — YouTube title, description, hashtags, tags (runs last)
    03_scene_breakdown.md
    04_asset_planning.md
    05_asset_acquisition.md
    08_animation_prompt.md     # step 8 — per-asset animation description for RunPod
    10_narration.md
    12_music.md
    16_creative_director.md
docs/                    # documentation
.keys                    # API keys — gitignored, never commit
workspace/               # generated workspaces — gitignored
output/                  # final videos — gitignored
```
