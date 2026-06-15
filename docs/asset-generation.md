# Asset Generation — Steps 6 & 7

Step 6 fetches and classifies assets; Step 7 generates the actual files (images, maps, charts) in three parallel sub-steps.

---

## Step 6 — Fetch Assets

`run_fetch_assets()` is implemented inline in `automate.py`. It parses `asset_acquisition.md` and writes a spec file or downloads content for each asset:

| Asset type | Action |
|-----------|--------|
| `ai_video` | Writes `generated.txt` with the Imagen 4 prompt |
| `map` | Writes `map_spec.json` with coordinates and marker data |
| `chart` | Writes `chart_spec.json` with chart type and data |
| `photo` / `video` | Downloads from Pexels API |

All assets are written to `{workspace}/assets/scene_X/asset_Y/`.

---

## Step 7a — Imagen 4 Image Generation

Generates AI images for every `ai_video` asset that has a `generated.txt` prompt file.

### `run_imagen_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `generated.txt` files
2. For each file — skip if `image.png` already exists (resumability)
3. Call Imagen 4:

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GEMINI_API_KEY)
response = client.models.generate_images(
    model=IMAGEN_MODEL,   # "imagen-4.0-generate-001"
    prompt=image_prompt,
    config=types.GenerateImagesConfig(number_of_images=1),
)
```

4. Save as `image.png` in the same directory as `generated.txt`
5. Log: `scene_X/asset_Y → image.png`

---

## Step 7b — Map Generation

Renders geographic maps from `map_spec.json` files written by Step 6.

### Asset manifest format

Step 4/5 prompts must produce map entries in this format:

```json
{
  "type": "map",
  "location": "Berlin, Germany",
  "lat": 52.52,
  "lon": 13.405,
  "zoom": 10,
  "markers": [{"lat": 52.52, "lon": 13.405, "label": "Brandenburg Gate"}],
  "style": "dark"
}
```

### `run_map_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `map_spec.json` files
2. For each file — skip if `map.png` already exists (resumability)
3. Render with Folium → save as HTML → screenshot with headless Playwright → `map.png`
4. If `style` is set and `REPLICATE_API_KEY` is available, pass through FLUX.1 img2img for cinematic look

```python
import folium
from playwright.sync_api import sync_playwright

def render_map(spec: dict, output_dir: Path) -> Path:
    m = folium.Map(location=[spec["lat"], spec["lon"]], zoom_start=spec["zoom"])
    for marker in spec.get("markers", []):
        folium.Marker([marker["lat"], marker["lon"]], popup=marker["label"]).add_to(m)
    html_path = output_dir / "map.html"
    m.save(str(html_path))
    png_path = output_dir / "map.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"file://{html_path}")
        page.screenshot(path=str(png_path))
        browser.close()
    return png_path
```

---

## Step 7c — Chart Generation

Renders data charts from `chart_spec.json` files written by Step 6.

### Asset manifest format

```json
{
  "type": "chart",
  "chart_type": "bar",
  "title": "GDP Growth 2015–2024",
  "data": {"labels": ["2015", "2016", "2017"], "values": [2.1, 2.3, 1.8]},
  "style": "cinematic"
}
```

Supported `chart_type` values: `bar`, `line`, `pie`, `area`.

### `run_chart_generation(ws)`

1. Scan `{workspace}/assets/` recursively for all `chart_spec.json` files
2. For each file — skip if `chart.png` already exists (resumability)
3. Render with matplotlib on a dark background → `chart.png`
4. If `style` is set and `REPLICATE_API_KEY` is available, pass through FLUX.1 img2img

```python
import matplotlib.pyplot as plt

def render_chart(spec: dict, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(16, 9), facecolor="black")
    ax.set_facecolor("black")
    ax.tick_params(colors="white")
    ax.title.set_color("white")
    labels = spec["data"]["labels"]
    values = spec["data"]["values"]
    if spec["chart_type"] == "bar":
        ax.bar(labels, values, color="#4A90D9")
    elif spec["chart_type"] == "line":
        ax.plot(labels, values, color="#4A90D9", linewidth=2, marker="o")
    ax.set_title(spec["title"])
    out = output_dir / "chart.png"
    fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="black")
    plt.close()
    return out
```
