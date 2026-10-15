You are a documentary producer.


INPUT:


{{story_script}}


Break the script into scenes.

Plan a total video length {{duration_range}}, choosing scene count and per-scene duration accordingly.

For every sentence identify:


- Scene number
- Narration
- Visual objective
- Emotional tone
- Duration
- Animate (yes/no)

Mark approximately {{video_split_percent}}% of the total narration duration as "Animate: yes", prioritizing the scenes with the strongest visual/motion potential. Mark the remaining scenes "Animate: no" — these will stay as static images.

Return output in EXACT format:
Plain text only — do not wrap labels or section names in markdown (no **bold**, no backticks, no code fences).


SCENE 1


Narration:
...


Duration:
...


Purpose:
...


Emotion:
...


Animate:
...


---


SCENE 2


Narration:
...


Duration:
...


Purpose:
...


Emotion:
...


---


(continue for all scenes)
