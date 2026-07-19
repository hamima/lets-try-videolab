# Scaffolding — `automate.py`

Core structure: entry point, configuration constants, CLI parsing, workspace management, and state tracking.

## Configuration Constants

```python
GEMINI_API_KEY        = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL          = "gemini-2.5-pro"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"   # used on 429 quota errors

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL   = "eleven_v3"

IMAGEN_MODEL = "imagen-4.0-generate-001"

PEXELS_API_KEY  = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

RUNPOD_API_KEY  = os.environ.get("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT = "https://api.runpod.ai/v2/YOUR_ENDPOINT_ID/run"  # TODO: replace
RUNPOD_MODEL    = "wan2.1"                                          # TODO: replace

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
python automate.py                                    # full run — resumes latest workspace
python automate.py --new                              # full run — always creates a fresh workspace
python automate.py --step 3 --workspace 200619        # run step 3 (skip if output exists)
python automate.py --step 3 --workspace 200619 --new  # force re-run step 3
python automate.py --step 1 --new                     # create fresh workspace and run step 1
python automate.py --status --workspace 200619        # print step status table and exit
```

**Rules:**
- `--workspace` is required with `--step` and `--status`
- `--step` respects existing output — skips the step if already done; use `--new` to force re-run
- Exception: `--step 1 --new` (no `--workspace`) creates a fresh workspace

**Step 7 special behaviour (Image Acquisition):**

| Command | Behaviour |
|---------|-----------|
| `--step 7 --workspace <id>` | Always runs — checks every asset in every scene; skips assets that already have `image.jpg` or `image.png`; generates only the missing ones |
| `--step 7 --workspace <id> --new` | Deletes all `image.png`, `image.jpg`, and `blocked.txt` files across all scenes first, then regenerates everything from scratch |

Step 7 is the only step that always runs when called via `--step` regardless of whether any output exists, because its output is per-asset (not a single file). All other steps follow the standard skip-if-output-exists rule.

```python
parser.add_argument("--step")
parser.add_argument("--status",    action="store_true")
parser.add_argument("--new",       action="store_true")
parser.add_argument("--workspace", help="time ID of a specific workspace, e.g. 200619")
```

## Domain Selection Menu

At startup, print a numbered list of `SUPPORTED_DOMAINS`. Accept only a valid number — loop until one is entered. The chosen domain determines the prompt directory, voice ID, and workspace path.

## Workspace Creation

Workspaces live at `workspace/{domain}/YYYY-MM-DD_HHMMSS/`. Each run creates its own timestamped folder — previous workspaces are never overwritten.

| Flag | Behaviour |
|------|-----------|
| _(none)_ | Resume the most recent workspace for the domain; create one if none exists |
| `--new` | Always create a fresh timestamped workspace |
| `--workspace <id>` | Target a specific workspace by its time identifier (e.g. `200619` from `2026-06-12_200619`) |

### Workspace lookup helpers

- `latest_workspace(domain)` — returns the most recent timestamped folder for the domain.
- `find_workspace(domain, identifier)` — searches all timestamped folders for one whose name contains the given identifier. Raises `RuntimeError` if zero or more than one match is found.

### `--step` workspace resolution

1. If `--new` → create a fresh workspace.
2. Else if `--workspace <id>` → call `find_workspace(domain, id)`; exit on error.
3. Else → call `latest_workspace(domain)`; if no workspace exists and step is `1`, create one; otherwise exit with an error.

## State File

`{workspace}/pipeline_state.json` tracks run progress:

```json
{
  "completed": ["1", "2", "3"],
  "failed": [],
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "domain": "political"
}
```

Helpers: `load_state()` / `save_state()`.

- Before running a step: check if its output file already exists → skip and log "already done"
- After successful step: append step ID to `completed`
- On exception: append to `failed`, print error, continue to next step (pipeline does not abort)
- Failed steps show `[!]` in `--status` and can be retried with `--step N`
