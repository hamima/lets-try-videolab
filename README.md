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
python automate.py           # full run
python automate.py --step 7a # re-run a single step
python automate.py --status  # show step status table
```

## Domains

`political` · `general_knowledge` · `science` · `business` · `history` · `sports` · `technology`

Each domain has its own prompt files under `prompts/{domain}/` and a dedicated ElevenLabs voice.

## API Keys

Copy `.keys`, fill in your values, and `source .keys` before each session:

| Key | Service |
|-----|---------|
| `GEMINI_API_KEY` | Google AI Studio / Vertex AI |
| `ELEVENLABS_API_KEY` | ElevenLabs |
| `PEXELS_API_KEY` | Pexels |
| `PIXABAY_API_KEY` | Pixabay |

## Documentation

| Doc | Contents |
|-----|----------|
| [Pipeline Overview](docs/pipeline-overview.md) | Full flow diagram, key decisions, execution order |
| [Scaffolding](docs/scaffolding.md) | CLI args, workspace layout, state file, domain/voice config |
| [LLM Steps](docs/llm-steps.md) | Gemini runner, all text-generation steps (1–5, 8, 10, 13), platform metadata (2b) |
| [Asset Generation](docs/asset-generation.md) | Step 6 fetch, Step 7a Imagen 4, Step 7b maps, Step 7c charts |
| [Audio Generation](docs/audio-generation.md) | Step 9 ElevenLabs TTS, Step 11 music generation |
| [Assembly](docs/assembly.md) | Step 14 — ffmpeg assembly via `assemble.py` |

## Project Structure

```
automate.py              # main pipeline script
pipeline.py              # original manual pipeline (reference)
prompts/
  {domain}/
    01_research.md
    02_story.md
    02b_platform_metadata.md   # YouTube title, description, hashtags, tags
    03_scene_breakdown.md
    04_asset_planning.md
    05_asset_acquisition.md
    08_narration.md
    10_music.md
    13_creative_director.md
docs/                    # documentation
.keys                    # API keys — gitignored, never commit
workspace/               # generated workspaces — gitignored
output/                  # final videos — gitignored
```
