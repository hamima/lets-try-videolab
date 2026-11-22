#!/usr/bin/env python3
"""
Step 17: Frame-exact final assembly.

Alignment is built in by construction, rejected at preflight, and verified
after render:

  * Absolute frame grid: scene start frame = round(start_sec * FPS) from
    narration_timing.json. Never a running sum of durations, so rounding error
    cannot accumulate. Each scene ends where the next begins (no gaps/overlaps).
  * Narration decides scene length: the slot beats the clip's duration_sec.
    Long clips are trimmed, short clips hold their last frame. Never stretched.
  * Narration is untouched: decoded once, placed at t=0, no per-scene cutting.
  * One sample grid: all audio is 48 kHz, exactly total_frames * 1600 samples.
    Music/sfx are placed at absolute-frame sample offsets.
  * One encode: single filter graph, one mux, fixed threads, bitexact flags.
    setpts=N/(FPS*TB) re-stamps every frame from its index.

Reads:  <ws>/edl.json, narration_timing.json, narration.mp3, music.wav, assets/
Writes: <ws>/output/final_video.mp4

Usage:  assemble.py [--preflight-only | --verify-only]
Exit code is non-zero if preflight or verification fails.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).parent.parent
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", BASE_DIR / "workspace"))
OUTPUT_DIR = WORKSPACE / "output"
SFX_DIR = BASE_DIR / "sfx"
FONT_PATH = str(BASE_DIR / "fonts" / "NotoSansDevanagari-Bold.ttf")

W, H, FPS = 1920, 1080, 30
SR = 48000
SPF = SR // FPS  # samples per frame (1600)
NARRATION_TOLERANCE_SEC = 0.15
MAX_START_OFFSET_SEC = 0.025

MUSIC_SPEECH_GAIN = 0.12
MUSIC_PAUSE_GAIN = 0.35
DUCK_FADE_SEC = 0.3
MUSIC_FADE_OUT_SEC = 1.0
SFX_BASE_VOLUME = 0.4

KNOWN_EFFECTS = {"speed", "zoom_punch"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

TEXT_STYLES = {
    "dramatic_center": dict(font_size=72, color=(255, 255, 255, 255), position="center", bg_type="gradient", shadow=True),
    "stat_lower_third": dict(font_size=54, color=(255, 255, 255, 255), position="lower_left", bg_type="pill", shadow=False),
    "name_tag": dict(font_size=42, color=(255, 255, 255, 255), position="lower_left", bg_type="bar", shadow=False),
    "quote": dict(font_size=48, color=(240, 240, 240, 255), position="center", bg_type="none", shadow=True),
    "location": dict(font_size=36, color=(255, 255, 255, 255), position="top_right", bg_type="pill", shadow=False),
}


class PreflightError(Exception):
    pass


# ----------------------------------------------------------------------------
# ffmpeg helpers
# ----------------------------------------------------------------------------

def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def probe_duration(path: Path):
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", str(path)], text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def decode_audio(path: Path) -> np.ndarray:
    """Decode to float32 stereo @ SR, shape (n, 2)."""
    r = _run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
              "-ac", "2", "-ar", str(SR), "-"])
    if r.returncode != 0:
        raise RuntimeError(f"cannot decode {path}: {r.stderr.decode()[-300:]}")
    return np.frombuffer(r.stdout, dtype="<f4").reshape(-1, 2).copy()


# ----------------------------------------------------------------------------
# Planning (pure; no rendering)
# ----------------------------------------------------------------------------

def normalize_asset_path(p):
    if not p:
        return p
    p = re.sub(r"assets/SCENE[ _](\d+)/", lambda m: f"assets/scene_{m.group(1)}/", p)
    if not p.startswith("assets/") and p.startswith("scene_"):
        p = "assets/" + p
    return p


def resolve_asset(ws: Path, rel: str, scene_id: int):
    """Resolve an EDL path; tolerate asset_K vs asset_<scene>.K folder naming."""
    rel = normalize_asset_path(rel)
    cand = ws / rel
    if cand.exists():
        return cand
    m = re.match(r"assets/scene_(\d+)/asset_(\d+)(?:\.(\d+))?/(.+)$", rel)
    if m:
        s, a1, a2, fname = m.groups()
        k = a2 or a1
        base = ws / "assets" / f"scene_{s}" / f"asset_{s}.{k}"
        for name in (fname, "animated.mp4", "image.png"):
            if (base / name).exists():
                return base / name
    return None


def load_edl_scenes(edl):
    """Accept the flat-list EDL or the legacy {project, timeline} form."""
    scenes = edl["timeline"] if isinstance(edl, dict) else edl
    out = []
    for e in scenes:
        if "clips" not in e:  # legacy single-asset form
            a = e.get("asset", {})
            e = dict(e, clips=[{
                "path": a.get("path"), "type": a.get("type", "video"),
                "trim_start_sec": a.get("trim_start_sec", 0),
                "trim_end_sec": a.get("trim_end_sec"),
                "duration_sec": e.get("duration_sec"),
                "effects": e.get("effects", {})}])
        out.append(e)
    return out


def build_plan(ws: Path, edl, timing):
    """Return (plan, errors, warnings). plan is None if errors."""
    errors, warnings = [], []
    scenes = load_edl_scenes(edl)
    t_scenes = timing["scenes"]

    edl_ids = [s["scene_id"] for s in scenes]
    t_ids = [s["scene_id"] for s in t_scenes]
    if edl_ids != t_ids:
        errors.append(f"EDL scene ids {edl_ids} != timing scene ids {t_ids}")
        return None, errors, warnings
    if timing.get("scene_count") != len(t_scenes):
        errors.append(f"timing scene_count={timing.get('scene_count')} but {len(t_scenes)} scenes listed")

    total_frames = round(timing["total_duration_sec"] * FPS)
    starts = [round(s["start_sec"] * FPS) for s in t_scenes]

    # gaps / overlaps in the timing file itself
    for a, b in zip(t_scenes, t_scenes[1:]):
        gap = b["start_sec"] - a["end_sec"]
        if abs(gap) > 1.0 / FPS:
            kind = "gap" if gap > 0 else "overlap"
            errors.append(f"scene {a['scene_id']}->{b['scene_id']}: {kind} of {abs(gap):.3f}s")
    if starts and starts[0] != 0:
        errors.append(f"first scene starts at frame {starts[0]}, expected 0")
    ends = starts[1:] + [total_frames]
    last_end = round(t_scenes[-1]["end_sec"] * FPS)
    if abs(last_end - total_frames) > 1:
        errors.append(f"last scene ends at frame {last_end} but total is {total_frames}")

    plan = {"total_frames": total_frames, "scenes": []}
    for sc, f0, f1 in zip(scenes, starts, ends):
        n = f1 - f0
        sid = sc["scene_id"]
        if n < 1:
            errors.append(f"scene {sid}: slot is {n} frames")
            continue
        clips = sc["clips"]
        durs = [float(c.get("duration_sec") or 0) for c in clips]
        if sum(durs) <= 0:
            durs = [1.0] * len(clips)
        if abs(sum(durs) - n / FPS) > 1.0 / FPS and len(clips) > 1:
            warnings.append(f"scene {sid}: clip durations sum {sum(durs):.2f}s != slot {n / FPS:.2f}s; rescaled to slot")
        if n < len(clips):
            errors.append(f"scene {sid}: {len(clips)} clips do not fit in {n} frames")
            continue

        cum, bounds = 0.0, [0]
        for d in durs:
            cum += d
            bounds.append(round(n * cum / sum(durs)))
        bounds[-1] = n
        for i in range(1, len(bounds)):  # at least 1 frame per clip
            bounds[i] = max(bounds[i], bounds[i - 1] + 1)
        if bounds[-1] != n:
            errors.append(f"scene {sid}: cannot give every clip a frame")
            continue

        cplans = []
        for i, c in enumerate(clips):
            eff = c.get("effects") or {}
            for k in eff:
                if k not in KNOWN_EFFECTS:
                    warnings.append(f"scene {sid} clip {i}: unknown effect '{k}' ignored")
            speed = float(eff.get("speed") or 1.0)
            if speed <= 0:
                errors.append(f"scene {sid} clip {i}: invalid speed {speed}")
                speed = 1.0
            ctype = c.get("type", "video")
            path = None
            if ctype != "placeholder" and c.get("path"):
                path = resolve_asset(ws, c["path"], sid)
                if path is None:
                    errors.append(f"scene {sid} clip {i}: missing file {c['path']}")
            kind = "placeholder" if path is None else ("image" if path.suffix.lower() in IMAGE_EXT else "video")
            trim_start = float(c.get("trim_start_sec") or 0)
            trim_end = c.get("trim_end_sec")
            cn = bounds[i + 1] - bounds[i]
            if kind == "video":
                dur = probe_duration(path)
                if dur is None:
                    errors.append(f"scene {sid} clip {i}: unreadable video {path.name}")
                else:
                    avail = dur if trim_end is None else min(float(trim_end), dur)
                    avail_frames = int((avail - trim_start) / speed * FPS)
                    if avail_frames < 1:
                        errors.append(f"scene {sid} clip {i}: trim_start {trim_start}s is beyond clip end")
                    elif avail_frames < cn:
                        warnings.append(f"scene {sid} clip {i}: FREEZE - source has {avail_frames} frames, "
                                        f"needs {cn}; holding last frame for {cn - avail_frames}")
                    elif avail_frames > cn + 1:
                        warnings.append(f"scene {sid} clip {i}: TRIM - {avail_frames} source frames cut to {cn}")
            cplans.append(dict(
                scene_id=sid, index=i, kind=kind, path=path, trim_start=trim_start,
                trim_end=None if trim_end is None else float(trim_end), speed=speed,
                punch=eff.get("zoom_punch"), f0=f0 + bounds[i], n=cn))

        overlays = []
        for ov in sc.get("text_overlays") or []:
            o0 = min(n, max(0, round(float(ov.get("start_sec", 0)) * FPS)))
            o1 = min(n, round(float(ov.get("end_sec", n / FPS)) * FPS))
            if ov.get("text") and o1 > o0:
                overlays.append(dict(text=ov["text"], style=ov.get("style", "dramatic_center"),
                                     anim=ov.get("animation", "none"), f0=f0 + o0, n=o1 - o0))
        sfx = [dict(name=s.get("name", ""), volume=float(s.get("volume", 0.5)),
                    frame=f0 + min(n - 1, max(0, round(float(s.get("at_sec", 0)) * FPS))))
               for s in sc.get("sfx") or []]
        plan["scenes"].append(dict(scene_id=sid, f0=f0, n=n, clips=cplans, overlays=overlays, sfx=sfx))

    return (None if errors else plan), errors, warnings


def preflight(ws: Path):
    """Raises PreflightError (listing every problem) before anything renders."""
    errors, warnings = [], []
    for name in ("edl.json", "narration_timing.json", "narration.mp3"):
        if not (ws / name).exists():
            errors.append(f"missing {name}")
    if errors:
        raise PreflightError("\n".join(errors))
    edl = json.loads((ws / "edl.json").read_text())
    timing = json.loads((ws / "narration_timing.json").read_text())

    real = probe_duration(ws / "narration.mp3")
    if real is None:
        errors.append("narration.mp3 is unreadable")
    elif abs(real - timing["total_duration_sec"]) > NARRATION_TOLERANCE_SEC:
        errors.append(f"narration.mp3 is {real:.2f}s but timing says {timing['total_duration_sec']}s "
                      f"(timing made for a different audio file?)")

    plan, e, w = build_plan(ws, edl, timing)
    errors += e
    warnings += w
    if not (ws / "music.wav").exists():
        warnings.append("music.wav not found; rendering without music")
    for s in (plan or {}).get("scenes", []):
        for sf in s["sfx"]:
            if _find_sfx(sf["name"]) is None:
                warnings.append(f"scene {s['scene_id']}: sfx '{sf['name']}' not found, skipped")
    if errors:
        raise PreflightError("\n".join(errors))
    return plan, timing, warnings


# ----------------------------------------------------------------------------
# Audio: one numpy mix on the 48 kHz / 1600-samples-per-frame grid
# ----------------------------------------------------------------------------

def _find_sfx(name):
    for ext in (".wav", ".mp3", ".ogg"):
        p = SFX_DIR / f"{name}{ext}"
        if p.exists():
            return p
    return None


def _fit(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) >= n:
        return x[:n]
    return np.vstack([x, np.zeros((n - len(x), 2), dtype=np.float32)])


def ducking_gain(n_samples, silences):
    """Music gain per sample: low during speech, higher in pauses, smoothed."""
    rate = 1000
    n = int(np.ceil(n_samples / SR * rate)) + 1
    env = np.full(n, MUSIC_SPEECH_GAIN, dtype=np.float64)
    for s in silences:
        a, b = int(s["start"] * rate), int(s["end"] * rate)
        env[max(0, a):max(0, min(n, b))] = MUSIC_PAUSE_GAIN
    k = max(1, int(DUCK_FADE_SEC * rate))
    env = np.convolve(np.pad(env, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    return np.interp(np.arange(n_samples) / SR, np.arange(n) / rate, env).astype(np.float32)


def build_audio(ws: Path, plan, timing) -> np.ndarray:
    total = plan["total_frames"] * SPF
    mix = _fit(decode_audio(ws / "narration.mp3"), total)  # untouched, from t=0

    music_path = ws / "music.wav"
    if music_path.exists():
        m = decode_audio(music_path)
        if len(m) < total:  # loop short music
            m = np.tile(m, (int(np.ceil(total / max(1, len(m)))), 1))
        m = m[:total].copy()
        fade = min(total, int(MUSIC_FADE_OUT_SEC * SR))
        m[total - fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
        mix += m * ducking_gain(total, timing.get("all_silences", []))[:, None]

    for sc in plan["scenes"]:
        for sf in sc["sfx"]:
            p = _find_sfx(sf["name"])
            if p is None:
                continue
            a = decode_audio(p) * (sf["volume"] * SFX_BASE_VOLUME)
            off = sf["frame"] * SPF
            seg = a[:max(0, total - off)]
            mix[off:off + len(seg)] += seg

    return np.clip(mix, -1.0, 1.0)


def write_wav(path: Path, x: np.ndarray):
    pcm = (x * 32767.0).round().astype("<i2")
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ----------------------------------------------------------------------------
# Text overlay rendering (PNG)
# ----------------------------------------------------------------------------

def render_text_png(text, style_name, out: Path):
    from PIL import Image, ImageDraw, ImageFont
    st = TEXT_STYLES.get(style_name, TEXT_STYLES["dramatic_center"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, st["font_size"])
    except (IOError, OSError):
        font = ImageFont.load_default()
    bb = d.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pos = st["position"]
    if pos == "lower_left":
        x, y = 80, H - th - 120
    elif pos == "top_right":
        x, y = W - tw - 80, 60
    else:
        x, y = (W - tw) // 2, (H - th) // 2
    pad = 20
    bg = st["bg_type"]
    if bg == "gradient":
        hh = th + pad * 2
        for i in range(hh):
            a = int(180 * (1 - abs(i - hh / 2) / (hh / 2)))
            d.rectangle([x - pad * 3, y - pad + i, x + tw + pad * 3, y - pad + i + 1], fill=(0, 0, 0, a))
    elif bg == "pill":
        d.rounded_rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], radius=12, fill=(0, 0, 0, 180))
    elif bg == "bar":
        d.rectangle([x - pad * 2, y - pad, x + tw + pad * 2, y + th + pad], fill=(0, 0, 0, 200))
    if st["shadow"]:
        d.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 180))
    d.text((x, y), text, font=font, fill=st["color"])
    img.save(out)


# ----------------------------------------------------------------------------
# Video: one filter graph
# ----------------------------------------------------------------------------

def fill_filter():
    return (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W}:{H},setsar=1")


def clip_filter(c, in_label, out_label):
    """Filter chain for one sub-clip producing exactly c['n'] frames."""
    f = []
    if c["kind"] == "video" and c["trim_end"] is not None:
        f.append(f"trim=duration={max(0.0, c['trim_end'] - c['trim_start'])}")
    f.append(f"setpts=(PTS-STARTPTS)/{c['speed']}")
    f.append(f"fps={FPS}")
    f.append(fill_filter())
    p = c["punch"]
    if p:
        at, sc, dur = float(p.get("at_sec", 0)), float(p.get("scale", 1.15)), float(p.get("duration_sec", 0.3))
        z = f"(1+({sc}-1)*max(0,1-abs(t-{at})/({dur}/2)))"
        f.append(f"scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}")
    f.append("format=yuv420p")
    f.append(f"tpad=stop_mode=clone:stop_duration={c['n'] / FPS + 2}")  # hold last frame
    f.append(f"trim=end_frame={c['n']}")
    f.append("setpts=PTS-STARTPTS")
    return f"[{in_label}]" + ",".join(f) + f"[{out_label}]"


def render(ws: Path, plan, timing, out_path: Path, tmp: Path):
    total = plan["total_frames"]
    wav = tmp / "mix.wav"
    write_wav(wav, build_audio(ws, plan, timing))

    clip_inputs, ov_inputs, chains, labels = [], [], [], []
    for sc in plan["scenes"]:
        for c in sc["clips"]:
            idx = len(labels)
            if c["kind"] == "placeholder":
                clip_inputs += ["-f", "lavfi", "-i", f"color=c=0x0a0a0a:s={W}x{H}:r={FPS}"]
            elif c["kind"] == "image":
                clip_inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(c["path"])]
            else:
                clip_inputs += ["-ss", f"{c['trim_start']}", "-i", str(c["path"])]
            labels.append(f"v{idx}")
            chains.append(clip_filter(c, f"{idx}:v", f"v{idx}"))
    n_clips = len(labels)

    chains.append("".join(f"[{l}]" for l in labels) + f"concat=n={n_clips}:v=1:a=0[cat]")
    chains.append(f"[cat]setpts=N/({FPS}*TB)[base]")

    cur, ov_i = "base", 0
    for sc in plan["scenes"]:
        for ov in sc["overlays"]:
            png = tmp / f"ov{ov_i}.png"
            render_text_png(ov["text"], ov["style"], png)
            ov_inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
            in_idx = n_clips + 1 + ov_i  # +1 for the audio input appended below
            fade = ""
            if ov["anim"] in ("fade_scale", "slide_up"):
                fd = min(0.3, ov["n"] / FPS / 2)
                fade = (f",fade=t=in:st=0:d={fd}:alpha=1"
                        f",fade=t=out:st={ov['n'] / FPS - fd}:d={fd}:alpha=1")
            chains.append(f"[{in_idx}:v]format=rgba{fade},setpts=PTS-STARTPTS+{ov['f0']}/({FPS}*TB)[o{ov_i}]")
            chains.append(f"[{cur}][o{ov_i}]overlay=enable='between(n,{ov['f0']},{ov['f0'] + ov['n'] - 1})'"
                          f":eof_action=pass:shortest=1[m{ov_i}]")
            cur = f"m{ov_i}"
            ov_i += 1
    chains.append(f"[{cur}]trim=end_frame={total},setpts=N/({FPS}*TB)[vout]")

    audio_idx = n_clips

    script = tmp / "graph.txt"
    script.write_text(";\n".join(chains))
    cmd = (["ffmpeg", "-y", "-v", "error", "-threads", "4", "-filter_threads", "1"]
           + clip_inputs + ["-i", str(wav)] + ov_inputs
           + ["-/filter_complex", str(script),
              "-map", "[vout]", "-map", f"{audio_idx}:a",
              "-frames:v", str(total), "-r", str(FPS), "-fps_mode", "cfr",
              "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
              "-x264-params", "threads=4:sliced-threads=0",
              "-c:a", "aac", "-b:a", "192k", "-ar", str(SR),
              "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
              "-movflags", "+faststart", str(out_path)])
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + r.stderr.decode()[-2000:])
    return wav


# ----------------------------------------------------------------------------
# Post-render verification
# ----------------------------------------------------------------------------

VW, VH = 64, 36


def _gray_frames(cmd_in, vf, max_frames=None):
    cmd = ["ffmpeg", "-v", "error"] + cmd_in + ["-vf", vf + f",scale={VW}:{VH},format=gray"]
    if max_frames:
        cmd += ["-frames:v", str(max_frames)]
    cmd += ["-f", "rawvideo", "-"]
    r = _run(cmd)
    return np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, VH, VW).astype(np.float32)


def _err(a, b):
    return float(np.abs(a - b).mean())


def expected_boundary_frames(c):
    """(first, last) source frame of a sub-clip as the renderer should show them."""
    if c["kind"] == "placeholder":
        f = np.full((VH, VW), 10, dtype=np.float32)
        return f, f
    if c["kind"] == "image":
        fr = _gray_frames(["-i", str(c["path"])], fill_filter(), 1)
        return fr[0], fr[0]
    inp = ["-ss", f"{c['trim_start']}", "-i", str(c["path"])]
    pre = f"trim=duration={c['trim_end'] - c['trim_start']}," if c["trim_end"] is not None else ""
    fr = _gray_frames(inp, f"{pre}setpts=(PTS-STARTPTS)/{c['speed']},fps={FPS},{fill_filter()}", c["n"])
    return fr[0], fr[min(c["n"], len(fr)) - 1]


def verify(out_path: Path, plan, wav_path: Path = None):
    """Return list of failure strings (empty = pass)."""
    fails, info = [], []
    total = plan["total_frames"]

    r = _run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
              "-show_entries", "stream=nb_read_frames,start_time,duration,r_frame_rate",
              "-of", "json", str(out_path)], text=True)
    v = json.loads(r.stdout)["streams"][0]
    frames = int(v["nb_read_frames"])
    info.append(f"frames {frames}/{total}")
    if frames != total:
        fails.append(f"frame count {frames} != planned {total}")

    r = _run(["ffprobe", "-v", "error", "-select_streams", "a:0",
              "-show_entries", "stream=start_time,duration,sample_rate", "-of", "json", str(out_path)], text=True)
    a = json.loads(r.stdout)["streams"][0]
    vdur = float(v.get("duration") or frames / FPS)
    adur = float(a["duration"])
    info.append(f"video {vdur:.3f}s audio {adur:.3f}s")
    if abs(vdur - adur) > 1.0 / FPS:
        fails.append(f"audio/video length differ by {abs(vdur - adur) * 1000:.1f}ms (> 1 frame)")
    for nm, s in (("video", v), ("audio", a)):
        off = float(s.get("start_time") or 0)
        if abs(off) > MAX_START_OFFSET_SEC:
            fails.append(f"{nm} stream start offset {off * 1000:.1f}ms > {MAX_START_OFFSET_SEC * 1000:.0f}ms")
    info.append(f"start offsets v={float(v.get('start_time') or 0) * 1000:.1f}ms a={float(a.get('start_time') or 0) * 1000:.1f}ms")

    # audio content lag vs the planned mix (catches codec delay / shifted audio)
    if wav_path is not None and wav_path.exists():
        try:
            ref = decode_audio(wav_path)
            got = decode_audio(out_path)
            n = min(len(ref), len(got), SR * 30)
            e = lambda x: np.abs(x[:n, 0]).reshape(-1, 48).mean(axis=1)  # 1 ms envelope
            er, eg = e(ref), e(got)
            er, eg = er - er.mean(), eg - eg.mean()
            if er.std() > 1e-6:
                lags = range(-60, 61)
                best = max(lags, key=lambda L: float(np.dot(er[max(0, L):len(er) + min(0, L)],
                                                            eg[max(0, -L):len(eg) + min(0, -L)])))
                info.append(f"audio lag {best}ms")
                if abs(best) > MAX_START_OFFSET_SEC * 1000:
                    fails.append(f"audio content lag {best}ms vs planned mix")
        except Exception as ex:  # verification of a verifier aid must not mask real results
            info.append(f"audio lag check skipped ({ex})")

    # per sub-clip boundary frames
    rendered = _gray_frames(["-i", str(out_path)], "null", None)
    if len(rendered) != frames:
        fails.append(f"decoded {len(rendered)} frames but container reports {frames}")
    clips = [c for sc in plan["scenes"] for c in sc["clips"]]
    exp = [expected_boundary_frames(c) for c in clips]
    eps = 0.5
    checked = 0
    for j, c in enumerate(clips):
        a0, a1 = c["f0"], c["f0"] + c["n"] - 1
        if a1 >= len(rendered):
            fails.append(f"scene {c['scene_id']} clip {c['index']}: beyond rendered video")
            continue
        own_first, own_last = exp[j]
        if j:
            prev_last = exp[j - 1][1]
            if _err(rendered[a0], own_first) > _err(rendered[a0], prev_last) + eps:
                fails.append(f"scene {c['scene_id']} clip {c['index']}: first frame {a0} matches previous clip better")
            if _err(rendered[a0 - 1], prev_last) > _err(rendered[a0 - 1], own_first) + eps:
                fails.append(f"scene {c['scene_id']} clip {c['index']}: frame {a0 - 1} already shows this clip (cut early)")
        if j + 1 < len(clips):
            nxt_first = exp[j + 1][0]
            if _err(rendered[a1], own_last) > _err(rendered[a1], nxt_first) + eps:
                fails.append(f"scene {c['scene_id']} clip {c['index']}: last frame {a1} matches next clip better")
        checked += 1
    info.append(f"{checked}/{len(clips)} clip boundaries checked")
    print("  verify: " + "; ".join(info))
    return fails


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def run(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ws = WORKSPACE
    print("Preflight...")
    try:
        plan, timing, warnings = preflight(ws)
    except PreflightError as e:
        print("PREFLIGHT FAILED:\n" + "\n".join("  - " + x for x in str(e).splitlines()))
        return 2
    for w in warnings:
        print("  WARN:", w)
    print(f"  OK: {len(plan['scenes'])} scenes, {plan['total_frames']} frames "
          f"({plan['total_frames'] / FPS:.2f}s @ {FPS}fps)")
    if "--preflight-only" in argv:
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "final_video.mp4"
    with tempfile.TemporaryDirectory(prefix="assemble_") as td:
        tmp = Path(td)
        if "--verify-only" in argv:
            wav = None
        else:
            print(f"Rendering -> {out}")
            wav = render(ws, plan, timing, out, tmp)
        print("Verifying...")
        fails = verify(out, plan, wav)
    if fails:
        print("VERIFICATION FAILED:\n" + "\n".join("  - " + f for f in fails))
        return 3
    print("Verification passed. Done.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
