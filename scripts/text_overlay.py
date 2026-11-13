"""
scripts/text_overlay.py — shared Pillow/MoviePy text-overlay rendering,
extracted from assemble.py (step 17) so it can also be used by
generate_subtitles.py (step 18) without duplicating ~100 lines of rendering
code. Behavior for assemble.py's existing overlays (dramatic/lower-third/
name-tag/quote/location) is unchanged — this is a pure extraction plus the
new "subtitle" style/position used for burned-in captions.

Reads:  fonts/NotoSansDevanagari-Bold.ttf
"""

import numpy as np
from pathlib import Path

try:
   from moviepy import ImageClip, CompositeVideoClip
except ImportError:
   raise ImportError("MoviePy not found. Install with: pip install moviepy")

try:
   from PIL import Image, ImageDraw, ImageFont
except ImportError:
   raise ImportError("Pillow not found. Install with: pip install Pillow")


BASE_DIR = Path(__file__).parent.parent
FONTS_DIR = BASE_DIR / "fonts"
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
   # Burned-in narration captions (step 18) — small, bottom-center, no
   # flashy animation, just legible over whatever footage is playing.
   "subtitle": {
       "font_size": 48,
       "color": (255, 255, 255, 255),
       "position": "bottom_center",
       "bg_type": "bar",
       "shadow": False,
   },
}


def render_text_overlay(text, style_name, frame_size):
   """Render text (Latin or Devanagari) onto an RGBA image using Pillow.
   Supports multi-line text (PIL draws/measures embedded '\\n' natively)."""
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
   elif position == "bottom_center":
       x = (w - text_w) // 2
       y = h - text_h - 110
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


def apply_text_overlays(base_clip, overlays, scene_duration, frame_size):
   """Composite text overlays onto the base clip. *overlays* entries carry
   start_sec/end_sec relative to base_clip's own timeline (0 = base_clip's
   start) — callers compositing against a full-video timeline (e.g.
   generate_subtitles.py burning captions onto the whole assembled video)
   should pass absolute seconds consistently for both base_clip and overlays."""
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


       frame = render_text_overlay(text, style_name, frame_size)
       txt_clip = ImageClip(frame).with_duration(ov_duration)
       txt_clip = txt_clip.with_start(start_sec)
       txt_clip = apply_text_animation(txt_clip, animation, ov_duration)
       overlay_clips.append(txt_clip)


   if not overlay_clips:
       return base_clip


   return CompositeVideoClip([base_clip] + overlay_clips, size=frame_size)
