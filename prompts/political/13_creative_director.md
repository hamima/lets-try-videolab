You are a senior documentary film editor and creative director.

INPUT:
{{asset_inventory}}

NARRATION TIMING:
{{narration_timing}}

TASK:
Create a detailed Edit Decision List (EDL) that maps every narration scene to its visual asset with precise timing, transition type, and Ken Burns motion direction.

RULES:
- Every scene must be assigned exactly one primary asset.
- Timing must align precisely with narration_timing.json.
- Ken Burns motion must be specified for ai_image and ai_video assets.
- Output must be valid JSON — no markdown, no code fences, no explanation.
- Prefer ai_image and ai_video assets. Only use stock assets when no AI asset exists for that scene.

OUTPUT FORMAT:
Return a JSON array where each element represents one scene:

[
  {
    "scene": 1,
    "start_time": 0.0,
    "end_time": 10.5,
    "asset_path": "assets/scene_1/asset_1/image.png",
    "asset_type": "ai_image",
    "ken_burns": {
      "direction": "zoom_in",
      "start_scale": 1.0,
      "end_scale": 1.15
    },
    "transition_in": "fade",
    "transition_out": "cut"
  }
]

TRANSITION OPTIONS: fade, cut, dissolve, wipe_left, wipe_right
KEN_BURNS DIRECTIONS: zoom_in, zoom_out, pan_left, pan_right
For non ai_image/ai_video assets, set ken_burns to null.

Return ONLY the JSON array. No other text.
