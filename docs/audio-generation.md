# Audio Generation — Steps 11 & 13

Both audio steps use the ElevenLabs v3 API. They run after the asset track (steps 6–9) — the narration track depends on `story_script.md` (step 10) and the music track depends on `scene_plan.md` (step 12).

---

## Step 11 — Narration TTS

### `run_elevenlabs_tts(ws, state)`

1. Read `{workspace}/narration_script.txt`
2. Extract the `=== ELEVENLABS VERSION ===` section — everything after that marker
   - This section contains `<break time="2.0s"/>` between scenes and `<break time="1.5s"/>` mid-sentence, as produced by `10_narration.md`
   - No further tag injection needed — v3 interprets `<break time="Xs"/>` natively
3. Load `voice_id` from `pipeline_state.json`
4. Call ElevenLabs TTS API:

```python
import requests

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
payload = {
    "text": narration_text,
    "model_id": ELEVENLABS_MODEL,   # "eleven_v3"
    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
}
response = requests.post(url, json=payload, headers=headers)
```

5. Save response bytes to `{workspace}/narration.mp3`

---

## Step 13 — Music Generation

### `run_elevenlabs_music(ws)`

1. Read `{workspace}/music_prompt.txt`
2. Truncate to 450 characters if needed — ElevenLabs hard limit; print `[WARN]` if truncated
3. Call ElevenLabs sound-generation API (max 22s per request):

```python
url = "https://api.elevenlabs.io/v1/sound-generation"
payload = {"text": music_prompt, "duration_seconds": 22, "prompt_influence": 0.3}
```

4. Save the 22s clip to `{workspace}/music.wav`
5. Extend to 210s using ffmpeg — loop the clip and fade out over the final 10 seconds:

```bash
ffmpeg -stream_loop -1 -i music.wav -t 210 -af "afade=t=out:st=200:d=10" music_extended.wav
```

6. Replace `music.wav` with the extended version. If ffmpeg fails, keep the 22s clip and log a warning.

### Music prompt constraints (`12_music.md`, used by step 12)

- Must specify "instrumental only, no vocals, soft background music" — plays under narration at 15% volume
- Under 450 characters total (ElevenLabs hard limit) — aim for 300–420
- Describe a loopable emotional arc — the 22s clip repeats, so avoid abrupt endings
