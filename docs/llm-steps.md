# LLM Steps — Gemini

All text-generation steps share a single runner that loads a domain-specific prompt, injects workspace outputs as template variables, calls Gemini, and saves the result.

## `run_gemini_step(step_id, ws, state)`

1. Read `state["domain"]` to find the prompt directory
2. Load `prompts/{domain}/NN_name.md` via `resolve_prompt_file(step_id, domain)`
3. Replace `{{variable_name}}` placeholders with content from previous workspace files
4. Call `gemini_generate(prompt)` — auto-falls back to `gemini-2.0-flash` on 429
5. Write the response to the workspace as the step's output file

### Prompt file discovery

```python
def resolve_prompt_file(step_id: str, domain: str, prompt_file: str = None) -> Path:
    domain_dir = PROMPTS_DIR / domain
    if prompt_file:
        return domain_dir / prompt_file  # explicit override (rare, for edge cases)
    for f in domain_dir.iterdir():
        if re.match(rf"^0*{re.escape(step_id)}[_.]", f.name):
            return f
    raise FileNotFoundError(f"No prompt file for step {step_id} in {domain_dir}")
```

### Step → prompt → output mapping

| Step | Prompt file | Variables injected | Output file |
|------|-------------|-------------------|-------------|
| 1 | `01_research.md` | none | `research_dossier.md` |
| 2 | `02_story.md` | `{{research_dossier}}` | `story_script.md` |
| 2b | `02b_platform_metadata.md` | `{{story_script}}` | `platform_metadata.json` |
| 3 | `03_scene_breakdown.md` | `{{story_script}}` | `scene_plan.md` |
| 4 | `04_asset_planning.md` | `{{scene_plan}}` | `asset_manifest.md` |
| 5 | `05_asset_acquisition.md` | `{{asset_manifest}}` | `asset_acquisition.md` |
| 8 | `08_animation_prompt.md` | `{{ken_burns}}` + `{{visual_goal}}` + `{{asset_type}}` + `{{duration}}` + `{{story_excerpt}}` | `animated.txt` per static asset |
| 10 | `10_narration.md` | `{{story_script}}` | `narration_script.txt` |
| 12 | `12_music.md` | `{{scene_plan}}` | `music_prompt.txt` |
| 16 | `16_creative_director.md` | `{{asset_inventory}}` + `{{narration_timing}}` | `edl.json` |

### Gemini API call with quota fallback

```python
from google import genai
from google.genai.errors import ClientError

def gemini_generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        return client.models.generate_content(model=model, contents=prompt).text
    except ClientError as e:
        if e.code == 429 and model == GEMINI_MODEL:
            print(f"[WARN] Quota exhausted — falling back to {GEMINI_FALLBACK_MODEL}")
            return gemini_generate(prompt, model=GEMINI_FALLBACK_MODEL)
        raise
```

Step 13 output must be valid JSON — strip markdown code fences and validate with `json.loads()` before saving as `edl.json`.

---

## Step 2b — Platform Metadata

Generates YouTube publishing metadata from the story script. No Python library exists for this task — Gemini is used with a domain-specific prompt.

### Output: `platform_metadata.json`

```json
{
  "youtube": {
    "title": "Why Germany's Energy Gamble Failed Everyone",
    "description": "Germany bet billions on a green energy transition — and it backfired...\n\nWhat you'll learn:\n• Why the Energiewende plan collapsed\n• The political decisions that made it worse\n• What this means for Europe's energy future\n\n⏱ TIMESTAMPS\n\n🔔 Subscribe for more political documentaries every week.",
    "hashtags": ["#Politics", "#Germany", "#Energy", "#Documentary", "#Geopolitics"],
    "tags": ["germany energy crisis", "energiewende failure", "european energy policy", "political documentary", "green energy germany"]
  }
}
```

The `youtube` key is the only one populated now. `instagram` and `tiktok` keys will be appended to the same file when those platforms are added — no schema change needed.

### JSON validation

```python
raw = gemini_generate(prompt)
raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
data = json.loads(raw)   # raises on invalid JSON — step marked failed, run continues
```

Save via `json.dump` (not raw text).

### Prompt files per domain

Each domain has a tailored SEO persona at `prompts/{domain}/02b_platform_metadata.md`:

| Domain | Persona | Hashtag focus |
|--------|---------|--------------|
| political | Investigative journalism SEO specialist | #Politics #Documentary #Geopolitics |
| general_knowledge | Educational explainer SEO specialist | #Education #Learning #Facts |
| science | STEM documentary SEO specialist | #Science #Documentary #STEM |
| business | Business/finance SEO specialist | #Business #Finance #Entrepreneurship |
| history | Historical documentary SEO specialist | #History #Documentary #HistoryChannel |
| sports | Sports documentary SEO specialist | #Sports #Documentary #Athletics |
| technology | Tech/innovation SEO specialist | #Technology #AI #Innovation |

### Extending to IG and TikTok

Add `instagram` and `tiktok` prompt rules to the existing `02b_platform_metadata.md` files. The step runner, output file, and JSON schema require no changes.
