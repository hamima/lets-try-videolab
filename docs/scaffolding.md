# Scaffolding — `automate.py`

Core structure: entry point, configuration constants, CLI parsing, workspace management, and state tracking.

## Configuration Constants

```python
GEMINI_API_KEY        = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL          = "gemini-2.5-pro"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"   # used on 429 quota errors

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_MODEL   = "eleven_v3"

IMAGEN_MODEL = "imagen-4.0-generate-001"

REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY", "")   # for --assembler replicate
RUNPOD_API_KEY    = os.environ.get("RUNPOD_API_KEY", "")      # for --assembler runpod

PEXELS_API_KEY  = os.environ["PEXELS_API_KEY"]
PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]

DOMAIN_VOICE_MAP = {
    "political":         "pNInz6obpgDQGcFmaJgB",   # Adam
    "general_knowledge": "onwK4e9ZLuTAKqWW03F9",   # Daniel
    "science":           "N2lVS1w4EtoT3dr4eOWO",   # Callum
    "business":          "XB0fDUnXU5powFXDhCwa",   # Charlotte
    "history":           "IKne3meq5aSn9XLyUdCD",   # Charlie
    "sports":            "ErXwobaYiN019PkySvjV",    # Antoni
    "technology":        "pqHfZKP75CvOlQylNhV4",   # Bill
}

SUPPORTED_DOMAINS = list(DOMAIN_VOICE_MAP.keys())
```

API keys are loaded from the environment. Run `source .keys` before executing the pipeline.

## CLI

```
python automate.py                         # full run (ffmpeg assembler)
python automate.py --assembler replicate   # full run, Replicate assembler for Step 14
python automate.py --assembler runpod      # full run, RunPod assembler for Step 14
python automate.py --step 3               # re-run one step in the latest workspace
python automate.py --step 12b             # step IDs can be strings (e.g. 12b)
python automate.py --status               # print step table and exit
```

Use `argparse`. `--assembler` defaults to `ffmpeg`. All modes show the domain selection menu first.

```python
parser.add_argument("--assembler", choices=["ffmpeg", "replicate", "runpod"], default="ffmpeg")
parser.add_argument("--step")
parser.add_argument("--status", action="store_true")
```

## Domain Selection Menu

At startup, print a numbered list of `SUPPORTED_DOMAINS`. Accept only a valid number — loop until one is entered. The chosen domain determines the prompt directory, voice ID, and workspace path.

## Workspace Creation

Workspaces live at `workspace/{domain}/YYYY-MM-DD_HHMMSS/`.

- **Full run:** `latest_workspace(domain)` finds the most recent folder for that domain. If found, resume it. If not, create a fresh workspace and write `pipeline_state.json`.
- **`--step N` and `--status`:** also call `latest_workspace(domain)` to find the active workspace.

## State File

`{workspace}/pipeline_state.json` tracks run progress:

```json
{
  "completed": ["1", "2", "3"],
  "failed": [],
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "domain": "political",
  "assembler": "ffmpeg"
}
```

Helpers: `load_state()` / `save_state()`.

- Before running a step: check if its output file already exists → skip and log "already done"
- After successful step: append step ID to `completed`
- On exception: append to `failed`, print error, continue to next step (pipeline does not abort)
- Failed steps show `[!]` in `--status` and can be retried with `--step N`
