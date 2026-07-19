#!/usr/bin/env python3
"""
Step 8b: Split Narration Text Per Scene


Extracts per-scene narration text from scene_plan.md and writes individual
text files for manual TTS generation, including tone direction and expected duration.


Reads:  workspace/scene_plan.md
Writes: workspace/narration_scenes/scene_01.txt through scene_NN.txt


Usage:
   python scripts/split_narration.py
"""


import re
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent
WORKSPACE = BASE_DIR / "workspace"
OUTPUT_DIR = WORKSPACE / "narration_scenes"


# Documentary narration pace: ~140 words per minute (deliberate, authoritative)
WORDS_PER_MINUTE = 140




def extract_scene_data(scene_plan_path: Path):
   """Parse scene_plan.md to extract narration text, emotion, and duration per scene."""
   text = scene_plan_path.read_text()


   scenes = re.split(r"^SCENE \d+", text, flags=re.MULTILINE)
   scenes = [s for s in scenes if s.strip()]


   scene_data = []
   for scene_block in scenes:
       narration_match = re.search(r"Narration:\s*\n(.+?)(?:\n\n|\n[A-Z]|\Z)", scene_block, re.DOTALL)
       emotion_match = re.search(r"Emotion:\s*\n(.+?)(?:\n\n|\n---|\Z)", scene_block, re.DOTALL)


       narration = narration_match.group(1).strip() if narration_match else ""
       emotion = emotion_match.group(1).strip() if emotion_match else ""


       scene_data.append({
           "narration": narration,
           "emotion": emotion,
       })


   return scene_data




def get_tone_direction(emotion):
   """Map scene emotion to specific voice direction."""
   tone_map = {
       "Chaos and Intrigue": "Dramatic, slightly breathless. Start strong and punchy — grab attention immediately.",
       "Urgency": "Fast-paced, urgent. Lean forward in intensity, like breaking news.",
       "Curiosity": "Slower, quieter pivot. Lower pitch slightly — create a conspiratorial pause.",
       "Suspense": "Low, deliberate, ominous. Build tension with measured pacing.",
       "Sobering Reality": "Warm but serious. Nostalgic tone — describing something that once was stable.",
       "Grounded Stability": "Authoritative, matter-of-fact. Steady pace. Institutional narrator voice.",
       "Suspicion": "Hushed, conspiratorial. Slow down noticeably.",
       "Shock": "Sharp, clipped delivery. Slight disbelief in voice.",
       "Despair": "Gradual descent from neutral to grave. Slow the final phrase.",
       "Escalating Panic": "Building intensity throughout. Start measured, end with alarm.",
       "Suffocation": "Heavy, compressed tone. Speak as if weighed down.",
       "Threat": "Dark, foreboding. Measured menace.",
       "Aggression": "Forceful, punchy. Clip the consonants. Confrontational energy.",
       "High Tension": "Pressured, taut. Clipped delivery under strain.",
       "Impending Crisis": "Cold, stark. Deliver like a warning.",
       "Deep Cynicism": "Questioning, slightly sardonic. Slow, probing.",
       "Mystery": "Quiet, intimate. Almost whispering. Draw the listener in close.",
       "Betrayal": "Controlled anger underneath calm delivery. Bitter edge.",
       "Skepticism": "Dry, knowing tone. Slightly dismissive.",
       "Dilemma": "Grave, time-pressure in the voice. Clipped.",
       "Anxiety": "Rising pitch and pace. Everyday-person vulnerability.",
       "Sadness": "Soft, slow, elegiac. Almost mourning. Gentle delivery.",
       "Heavy Reflection": "Deep, measured, philosophical. Speak slowly. Give weight to every word.",
       "Thought-provoking": "Open-ended, lingering. Raise pitch slightly on the question.",
       # New emotions for Jaishankar/Hindi video
       "Curiosity & Intrepidation": "Mysterious, questioning. Start quiet then build with anticipation.",
       "High Stakes & Tension": "Intense, urgent. Convey the weight of a global crisis unfolding.",
       "Intrigue & Personal Connection": "Conspiratorial shift — from grand to intimate. Lower voice.",
       "Pressure & Anxiety": "Tight, compressed delivery. Convey being squeezed from all sides.",
       "Fear & Vulnerability": "Soft, worried. Everyday person's concern. Relatable anxiety.",
       "Defiance & Defensiveness": "Strong, proud entry. Rising confidence. Hero's arrival.",
       "Pride & Empowerment": "Full-chested, triumphant. Deliver the iconic quote with gravitas.",
       "Conflict & Criticism": "Harsh, confrontational tone from others. Reading accusations.",
       "Moral Dilemma & Friction": "Torn, balanced. Present both sides with weight.",
       "Risk & Strategic Suspense": "Calculated, tense. Walking a tightrope — controlled but dangerous.",
       "Extreme Danger & Unease": "Hushed alarm. Every word carries risk.",
       "Shock & Sudden Revelation": "Sharp pivot. Voice drops then hits hard with the reveal.",
       "Awe & Total Surprise": "Genuine astonishment. Let the revelation land with a pause.",
       "Validation & Astonishment": "Building triumph. The pieces click together.",
       "Sarcasm & Ultimate Vindication": "Wry, knowing. A satisfied 'I told you so' energy.",
       "Relief & Grounded Reality": "Warm, settled. Back to normalcy. Gentle smile in voice.",
       "Triumph & National Progress": "Proud, uplifting. Celebratory but grounded.",
       "Empowerment & Status": "Authoritative, grand. India has arrived.",
       "Deep Reflection & Skepticism": "Philosophical, questioning. Not all is perfect.",
       "Open-Ended Suspense": "Lingering, unresolved. Let the question hang in silence.",
   }
   return tone_map.get(emotion, f"Match the emotion: {emotion}. Deliver with conviction and clarity.")




def estimate_duration(narration_text):
   """Estimate speaking duration based on word count at documentary narration pace."""
   word_count = len(narration_text.split())
   duration = (word_count / WORDS_PER_MINUTE) * 60
   return round(max(duration, 3.0), 1)




def run():
   scene_plan_path = WORKSPACE / "scene_plan.md"


   if not scene_plan_path.exists():
       print(f"ERROR: {scene_plan_path} not found. Run Step 3 first.")
       return


   print("Splitting narration text per scene...")


   scene_data = extract_scene_data(scene_plan_path)
   print(f"  Found {len(scene_data)} scenes")


   OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


   total_duration = 0.0
   for i, scene in enumerate(scene_data, 1):
       narration = scene["narration"]
       emotion = scene["emotion"]
       tone = get_tone_direction(emotion)
       duration = estimate_duration(narration)
       total_duration += duration
       word_count = len(narration.split())


       output_path = OUTPUT_DIR / f"scene_{i:02d}.txt"
       content = (
           f"--- VOICE DIRECTION ---\n"
           f"Emotion: {emotion}\n"
           f"Tone: {tone}\n"
           f"Target duration: ~{duration}s ({word_count} words)\n"
           f"--- NARRATION ---\n"
           f"{narration}\n"
       )
       output_path.write_text(content)
       print(f"  Scene {i:2d}: {word_count:3d} words | ~{duration:4.1f}s | {emotion}")


   print(f"\n  Total estimated duration: {total_duration:.1f}s ({total_duration/60:.1f} min)")
   print(f"  Output: {OUTPUT_DIR}/")
   print(f"\n  Next: Generate MP3 for each scene in ElevenLabs.")
   print(f"        Use the VOICE DIRECTION at the top of each file to guide delivery.")
   print(f"        Save as scene_01.mp3, scene_02.mp3, etc. in the same folder.")
   print(f"\n  IMPORTANT: Only paste the text below '--- NARRATION ---' into ElevenLabs.")
   print(f"             The voice direction is for your reference only.")




if __name__ == "__main__":
   run()



