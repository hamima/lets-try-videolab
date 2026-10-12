#!/usr/bin/env python3
"""
Step 14: Final video assembly from EDL v2 with narration-locked timing,
multi-clip scenes, text overlays, SFX, zoom punches, and music ducking.


Uses narration_timing.json as the MASTER CLOCK.


Reads:  workspace/edl.json
       workspace/narration_timing.json
       workspace/narration.mp3
       workspace/music.wav
       assets/scene_X/...
       sfx/*.wav
       fonts/NotoSansDevanagari-Bold.ttf
Writes: output/final_video.mp4
"""


import json
import os
import re
import sys
import numpy as np
from pathlib import Path


try:
   from moviepy import (
       VideoFileClip, ImageClip, AudioFileClip, CompositeAudioClip,
       CompositeVideoClip, concatenate_videoclips, ColorClip,
   )
except ImportError:
   print("MoviePy not found. Install with: pip install moviepy")
   print("Also ensure ffmpeg is installed: brew install ffmpeg")
   sys.exit(1)


try:
   from PIL import Image, ImageDraw, ImageFont
except ImportError:
   print("Pillow not found. Install with: pip install Pillow")
   sys.exit(1)


BASE_DIR = Path(__file__).parent.parent
# WORKSPACE_DIR is set by backend/tasks.py's _run_script() to the per-run workspace
# (workspace/<domain>/<run_id>); fall back to the repo-root workspace/ for standalone use.
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))
ASSETS_DIR = WORKSPACE / "assets"
# Final output is global (not per-run) — matches tasks.py's _output_exists() treatment
# of "output/"-prefixed step outputs as BASE_DIR-relative.
OUTPUT_DIR = BASE_DIR / "output"
SFX_DIR = BASE_DIR / "sfx"
FONTS_DIR = BASE_DIR / "fonts"


TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
FPS = 30


MUSIC_VOLUME_DURING_SPEECH = 0.12
MUSIC_VOLUME_DURING_PAUSE = 0.35
DUCK_FADE_SEC = 0.3
SFX_BASE_VOLUME = 0.4


FONT_PATH = str(FONTS_DIR / "NotoSansDevanagari-Bold.ttf")


TEXT_STYLES = {
   "dramatic_center": {
       "font_size": 72,
       "color": (255, 255, 255, 255),
       "position": "center",
       "bg_type": "gradient",
       "shadow": True,
   },
   "stat_lower_third": {
       "font_size": 54,
       "color": (255, 255, 255, 255),
       "position": "lower_left",
       "bg_type": "pill",
       "shadow": False,
   },
   "name_tag": {
       "font_size": 42,
       "color": (255, 255, 255, 255),
       "position": "lower_left",
       "bg_type": "bar",
       "shadow": False,
   },
   "quote": {
       "font_size": 48,
       "color": (240, 240, 240, 255),
       "position": "center",
       "bg_type": "none",
       "shadow": True,
   },
   "location": {
       "font_size": 36,
       "color": (255, 255, 255, 255),
       "position": "top_right",
       "bg_type": "pill",
       "shadow": False,
   },
}




# ----------------------------
# PATH NORMALIZATION
# ----------------------------


def normalize_asset_path(path_str):
   """Fix common Gemini path mistakes."""
   if not path_str:
       return path_str
   path_str = re.sub(r'assets/SCENE\s+(\d+)/', lambda m: f'assets/scene_{m.group(1)}/', path_str)
   path_str = re.sub(r'assets/SCENE_(\d+)/', lambda m: f'assets/scene_{m.group(1)}/', path_str)
   if not path_str.startswith("assets/") and path_str.startswith("scene_"):
       path_str = "assets/" + path_str
   return path_str




# ----------------------------
# SCENE NORMALIZATION (v1 → v2 compat)
# ----------------------------


def normalize_scene(entry):
   """Convert legacy single-asset scene to multi-clip format."""
   if "clips" in entry:
       for clip in entry["clips"]:
           if "path" in clip:
               clip["path"] = normalize_asset_path(clip["path"])
       return entry
   asset = entry.get("asset", {})
   if asset.get("path"):
       asset["path"] = normalize_asset_path(asset["path"])
   clip_entry = {
       "path": asset.get("path"),
       "type": asset.get("type", "video"),
       "trim_start_sec": asset.get("trim_start_sec", 0),
       "trim_end_sec": asset.get("trim_end_sec"),
       "duration_sec": entry.get("_actual_duration", entry.get("duration_sec", 5)),
       "effects": entry.get("effects", {}),
   }
   entry["clips"] = [clip_entry]
   entry.setdefault("text_overlays", [])
   entry.setdefault("sfx", [])
   return entry




# ----------------------------
# VIDEO HELPERS
# ----------------------------


def resize_to_fill(clip, target_w, target_h):
   clip_aspect = clip.w / clip.h
   target_aspect = target_w / target_h
   if clip_aspect > target_aspect:
       new_height = target_h
       new_width = int(clip_aspect * target_h)
   else:
       new_width = target_w
       new_height = int(target_w / clip_aspect)
   clip = clip.resized((new_width, new_height))
   x_center = new_width // 2
   y_center = new_height // 2
   clip = clip.cropped(
       x1=x_center - target_w // 2,
       y1=y_center - target_h // 2,
       x2=x_center + target_w // 2,
       y2=y_center + target_h // 2,
   )
   return clip




def apply_zoom_punch(clip, punch_config):
   """Apply a quick emphasis zoom at a specific moment in the clip."""
   if not punch_config:
       return clip
   at = punch_config.get("at_sec", 0)
   scale = punch_config.get("scale", 1.15)
   dur = punch_config.get("duration_sec", 0.3)


   def zoom_func(t):
       dist = abs(t - at)
       half_dur = dur / 2
       if dist > half_dur:
           return 1.0
       progress = 1.0 - (dist / half_dur)
       return 1.0 + (scale - 1.0) * progress


   return clip.resized(zoom_func)




# ----------------------------
# SINGLE CLIP BUILDER
# ----------------------------


def build_single_clip(clip_data: dict, duration: float, scene_id: int):
   """Build a clip for one sub-clip entry."""
   clip_type = clip_data.get("type", "video")
   clip_path = clip_data.get("path")
   effects = clip_data.get("effects", {})


   if clip_type == "placeholder" or clip_path is None:
       clip = ColorClip(size=(TARGET_WIDTH, TARGET_HEIGHT), color=(10, 10, 10))
       return clip.with_duration(duration)


   asset_path = WORKSPACE / clip_path


   if not asset_path.exists():
       print(f"    WARNING - not found: {asset_path.name}, using black")
       clip = ColorClip(size=(TARGET_WIDTH, TARGET_HEIGHT), color=(10, 10, 10))
       return clip.with_duration(duration)


   if clip_type == "image":
       clip = ImageClip(str(asset_path))
       clip = resize_to_fill(clip, TARGET_WIDTH, TARGET_HEIGHT)
       ken_burns = effects.get("ken_burns")
       if ken_burns:
           intensity = ken_burns.get("intensity", 0.15)
           direction = ken_burns.get("direction", "zoom_in")
           if direction == "zoom_in":
               clip = clip.resized(lambda t: 1.0 + intensity * (t / duration))
           elif direction == "zoom_out":
               clip = clip.resized(lambda t: (1.0 + intensity) - intensity * (t / duration))
           elif direction == "pan_left":
               base_clip = clip.resized(1.0 + intensity)
               shift = int(TARGET_WIDTH * intensity)
               base_clip = base_clip.with_position(
                   lambda t: (-int(shift * (t / duration)), 0)
               )
               clip = base_clip
           elif direction == "pan_right":
               base_clip = clip.resized(1.0 + intensity)
               shift = int(TARGET_WIDTH * intensity)
               base_clip = base_clip.with_position(
                   lambda t: (-shift + int(shift * (t / duration)), 0)
               )
               clip = base_clip
       clip = clip.with_duration(duration)
       return clip


   # Video
   try:
       clip = VideoFileClip(str(asset_path))
   except (IOError, OSError):
       print(f"    WARNING - corrupted: {asset_path.name}, using black")
       clip = ColorClip(size=(TARGET_WIDTH, TARGET_HEIGHT), color=(10, 10, 10))
       return clip.with_duration(duration)


   trim_start = clip_data.get("trim_start_sec", 0)
   trim_end = clip_data.get("trim_end_sec", clip.duration)
   clip = clip.subclipped(trim_start, min(trim_end, clip.duration))


   speed = effects.get("speed", 1.0)
   if speed != 1.0 and speed > 0:
       clip = clip.with_speed_scaled(speed)


   if clip.duration < duration:
       loops_needed = int(duration / clip.duration) + 1
       clip = concatenate_videoclips([clip] * loops_needed)


   clip = clip.subclipped(0, duration)
   clip = resize_to_fill(clip, TARGET_WIDTH, TARGET_HEIGHT)
   clip = clip.without_audio()
   return clip




# ----------------------------
# TEXT OVERLAYS
# ----------------------------


def render_text_overlay(text, style_name, frame_size):
   """Render Hindi text onto RGBA image using Pillow."""
   style = TEXT_STYLES.get(style_name, TEXT_STYLES["dramatic_center"])
   w, h = frame_size
   img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
   draw = ImageDraw.Draw(img)


   font_size = style["font_size"]
   try:
       font = ImageFont.truetype(FONT_PATH, font_size)
   except (IOError, OSError):
       font = ImageFont.load_default()


   bbox = draw.textbbox((0, 0), text, font=font)
   text_w = bbox[2] - bbox[0]
   text_h = bbox[3] - bbox[1]


   position = style["position"]
   if position == "center":
       x = (w - text_w) // 2
       y = (h - text_h) // 2
   elif position == "lower_left":
       x = 80
       y = h - text_h - 120
   elif position == "top_right":
       x = w - text_w - 80
       y = 60
   else:
       x = (w - text_w) // 2
       y = (h - text_h) // 2


   bg_type = style.get("bg_type", "none")
   pad = 20
   if bg_type == "gradient":
       for i in range(text_h + pad * 2):
           alpha = int(180 * (1 - abs(i - (text_h + pad * 2) / 2) / ((text_h + pad * 2) / 2)))
           draw.rectangle(
               [x - pad * 3, y - pad + i, x + text_w + pad * 3, y - pad + i + 1],
               fill=(0, 0, 0, alpha)
           )
   elif bg_type == "pill":
       draw.rounded_rectangle(
           [x - pad, y - pad, x + text_w + pad, y + text_h + pad],
           radius=12, fill=(0, 0, 0, 180)
       )
   elif bg_type == "bar":
       draw.rectangle(
           [x - pad * 2, y - pad, x + text_w + pad * 2, y + text_h + pad],
           fill=(0, 0, 0, 200)
       )


   if style.get("shadow"):
       draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 180))


   draw.text((x, y), text, font=font, fill=style["color"])
   return np.array(img)




def apply_text_animation(clip, anim_name, duration):
   """Apply entrance/exit animation to a text overlay clip."""
   fade_in = 0.3
   fade_out = 0.3


   if anim_name in ("fade_scale", "slide_up"):
       try:
           from moviepy.video.fx import CrossFadeIn, CrossFadeOut
           clip = clip.with_effects([CrossFadeIn(fade_in), CrossFadeOut(fade_out)])
       except (ImportError, Exception):
           pass


   return clip




def apply_text_overlays(base_clip, overlays, scene_duration):
   """Composite text overlays onto the base clip."""
   if not overlays:
       return base_clip


   overlay_clips = []
   for ov in overlays:
       text = ov.get("text", "")
       style_name = ov.get("style", "dramatic_center")
       start_sec = ov.get("start_sec", 0)
       end_sec = ov.get("end_sec", scene_duration)
       animation = ov.get("animation", "none")
       ov_duration = end_sec - start_sec


       if ov_duration <= 0 or not text:
           continue


       frame = render_text_overlay(text, style_name, (TARGET_WIDTH, TARGET_HEIGHT))
       txt_clip = ImageClip(frame).with_duration(ov_duration)
       txt_clip = txt_clip.with_start(start_sec)
       txt_clip = apply_text_animation(txt_clip, animation, ov_duration)
       overlay_clips.append(txt_clip)


   if not overlay_clips:
       return base_clip


   return CompositeVideoClip([base_clip] + overlay_clips, size=(TARGET_WIDTH, TARGET_HEIGHT))




# ----------------------------
# MULTI-CLIP SCENE BUILDER
# ----------------------------


def build_scene_clip(scene_entry: dict, actual_duration: float):
   """Build a complete scene: multi-clip + text overlays + zoom punches."""
   scene_entry = normalize_scene(scene_entry)
   scene_id = scene_entry["scene_id"]
   clips_data = scene_entry["clips"]


   sub_clips = []
   for i, clip_data in enumerate(clips_data):
       clip_dur = clip_data.get("duration_sec", actual_duration / len(clips_data))
       clip = build_single_clip(clip_data, clip_dur, scene_id)
       punch = clip_data.get("effects", {}).get("zoom_punch")
       if punch:
           clip = apply_zoom_punch(clip, punch)
       sub_clips.append(clip)


   if len(sub_clips) == 1:
       scene_video = sub_clips[0]
   else:
       scene_video = concatenate_videoclips(sub_clips, method="compose")


   # Ensure scene matches exact narration duration
   if abs(scene_video.duration - actual_duration) > 0.2:
       scene_video = scene_video.subclipped(0, min(actual_duration, scene_video.duration))
       if scene_video.duration < actual_duration:
           black_pad = ColorClip(
               size=(TARGET_WIDTH, TARGET_HEIGHT), color=(10, 10, 10)
           ).with_duration(actual_duration - scene_video.duration)
           scene_video = concatenate_videoclips([scene_video, black_pad])


   scene_video = apply_text_overlays(scene_video, scene_entry.get("text_overlays", []), actual_duration)


   clip_count = len(clips_data)
   has_text = len(scene_entry.get("text_overlays", [])) > 0
   extras = []
   if clip_count > 1:
       extras.append(f"{clip_count} clips")
   if has_text:
       extras.append("text")
   extra_str = f" [{', '.join(extras)}]" if extras else ""
   print(f"  Scene {scene_id}: {actual_duration:.1f}s{extra_str}")


   return scene_video




# ----------------------------
# SFX
# ----------------------------


def find_sfx_file(name):
   """Find SFX file by name, checking wav/mp3/ogg extensions."""
   for ext in (".wav", ".mp3", ".ogg"):
       path = SFX_DIR / f"{name}{ext}"
       if path.exists():
           return path
   return None




def collect_sfx_audio(timeline):
   """Build positioned SFX AudioFileClips."""
   sfx_clips = []
   for scene in timeline:
       scene_start = scene.get("_actual_start", scene.get("start_time_sec", 0))
       for sfx in scene.get("sfx", []):
           sfx_name = sfx.get("name", "")
           sfx_path = find_sfx_file(sfx_name)
           if not sfx_path:
               continue
           try:
               audio = AudioFileClip(str(sfx_path))
               volume = sfx.get("volume", 0.5) * SFX_BASE_VOLUME
               audio = audio.with_volume_scaled(volume)
               audio = audio.with_start(scene_start + sfx.get("at_sec", 0))
               sfx_clips.append(audio)
           except Exception:
               pass
   return sfx_clips




# ----------------------------
# MUSIC DUCKING
# ----------------------------


def build_ducking_envelope(total_duration, silences):
   sample_rate = 1000
   num_samples = int(total_duration * sample_rate)
   envelope = np.full(num_samples, MUSIC_VOLUME_DURING_SPEECH)


   for silence in silences:
       start_idx = int(silence["start"] * sample_rate)
       end_idx = int(silence["end"] * sample_rate)
       start_idx = max(0, min(start_idx, num_samples - 1))
       end_idx = max(0, min(end_idx, num_samples - 1))
       envelope[start_idx:end_idx] = MUSIC_VOLUME_DURING_PAUSE


   fade_samples = int(DUCK_FADE_SEC * sample_rate)
   smoothed = np.copy(envelope)
   for i in range(1, num_samples):
       if abs(envelope[i] - envelope[i - 1]) > 0.01:
           region_start = max(0, i - fade_samples // 2)
           region_end = min(num_samples, i + fade_samples // 2)
           ramp = np.linspace(smoothed[region_start], envelope[region_end - 1],
                              region_end - region_start)
           smoothed[region_start:region_end] = ramp


   return smoothed




def apply_music_ducking(music_clip, envelope):
   sample_rate = 1000


   def volume_filter(get_frame, t):
       frame = get_frame(t)
       indices = np.clip((np.asarray(t) * sample_rate).astype(int), 0, len(envelope) - 1)
       gains = envelope[indices]
       if gains.ndim == 1:
           gains = gains[:, np.newaxis]
       return frame * gains


   return music_clip.transform(volume_filter, keep_duration=True)




# ----------------------------
# MAIN
# ----------------------------


def run():
   edl_path = WORKSPACE / "edl.json"
   timing_path = WORKSPACE / "narration_timing.json"


   if not edl_path.exists():
       print(f"ERROR: {edl_path} not found. Run Step 13 first.")
       sys.exit(1)


   print("Loading edit decision list...")
   with open(edl_path) as f:
       edl = json.load(f)


   timing_data = None
   if timing_path.exists():
       with open(timing_path) as f:
           timing_data = json.load(f)
       print(f"Narration timing loaded: {timing_data['total_duration_sec']}s, "
             f"{timing_data['scene_count']} scenes")
   else:
       print("WARNING: narration_timing.json not found — using EDL durations (less accurate)")


   project = edl["project"]
   timeline = edl["timeline"]
   edl_version = project.get("edl_version", 1)


   print(f"Project: {project['resolution']} @ {project['fps']}fps (EDL v{edl_version})")
   print(f"Scenes: {len(timeline)}")
   print()


   # Override EDL durations with actual narration timestamps
   if timing_data:
       timing_scenes = timing_data["scenes"]
       for i, entry in enumerate(timeline):
           if i < len(timing_scenes):
               ts = timing_scenes[i]
               entry["_actual_start"] = ts["start_sec"]
               entry["_actual_duration"] = ts["duration_sec"]
           else:
               entry["_actual_start"] = entry["start_time_sec"]
               entry["_actual_duration"] = entry["duration_sec"]
   else:
       for entry in timeline:
           entry["_actual_start"] = entry["start_time_sec"]
           entry["_actual_duration"] = entry["duration_sec"]


   # Build clips
   print("Building scene clips (narration-locked)...")
   clips = []
   for entry in timeline:
       clip = build_scene_clip(entry, entry["_actual_duration"])
       clips.append(clip)


   print("\nConcatenating timeline...")
   final_video = concatenate_videoclips(clips, method="compose")
   total_duration = final_video.duration
   print(f"Video duration: {total_duration:.1f}s")


   # Audio mixing
   print("\nMixing audio...")
   narration_path = WORKSPACE / "narration.mp3"
   music_path = WORKSPACE / "music.wav"


   audio_tracks = []


   if narration_path.exists():
       narration = AudioFileClip(str(narration_path))
       audio_tracks.append(narration)
       print(f"  Narration: {narration.duration:.1f}s")
   else:
       print("  WARNING: narration.mp3 not found")


   if music_path.exists():
       music = AudioFileClip(str(music_path))
       music = music.subclipped(0, min(total_duration, music.duration))


       if timing_data and "all_silences" in timing_data:
           print(f"  Music ducking: speech={MUSIC_VOLUME_DURING_SPEECH}, pause={MUSIC_VOLUME_DURING_PAUSE}")
           envelope = build_ducking_envelope(total_duration, timing_data["all_silences"])
           music = apply_music_ducking(music, envelope)
       else:
           flat_volume = project.get("music_volume", 0.15)
           music = music.with_volume_scaled(flat_volume)
           print(f"  Music: flat volume @ {flat_volume}")


       audio_tracks.append(music)
       print(f"  Music: {music.duration:.1f}s")
   else:
       print("  WARNING: music.wav not found")


   # SFX
   sfx_clips = collect_sfx_audio(timeline)
   if sfx_clips:
       audio_tracks.extend(sfx_clips)
       print(f"  SFX: {len(sfx_clips)} sound effects loaded")


   if audio_tracks:
       final_audio = CompositeAudioClip(audio_tracks)
       final_video = final_video.with_audio(final_audio)


   # Export
   OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
   output_path = OUTPUT_DIR / "final_video.mp4"
   print(f"\nExporting to {output_path}...")


   final_video.write_videofile(
       str(output_path),
       fps=FPS,
       codec="libx264",
       audio_codec="aac",
       bitrate="8000k",
       preset="medium",
       threads=4,
   )


   print(f"\nDone! Output: {output_path}")
   print(f"Duration: {total_duration:.1f}s")


   final_video.close()
   for c in clips:
       c.close()




if __name__ == "__main__":
   run()



