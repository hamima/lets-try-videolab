"""
backend/subtitles.py — pure, unit-testable logic behind pipeline step 18
(Subtitles): turning either ElevenLabs character-level alignment data (the
primary path) or narration_timing.json's scene/pause data (the fallback,
used when no alignment exists — OpenRouter TTS, or a pre-existing run from
before this feature) into a list of timed, scene-grouped captions, plus the
subtitle.md parser/serializer shared with the web app's editable viewer.

Imported directly by backend/tests/, and by scripts/generate_subtitles.py
(the actual step-18 subprocess entrypoint) via the same
sys.path.insert(backend/) pattern scripts/migrate_workspaces_to_users.py
already uses for backend/workspace_migration.py.
"""

from __future__ import annotations

import re
from typing import Optional, TypedDict


class Caption(TypedDict):
    scene_id: int
    start_sec: float
    end_sec: float
    text: str


class WordTiming(TypedDict):
    text: str
    start: float
    end: float


MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MAX_CHARS_PER_CAPTION = MAX_CHARS_PER_LINE * MAX_LINES
MIN_DURATION_SEC = 1.0
MAX_DURATION_SEC = 6.0

SENTENCE_END_RE = re.compile(r'[.!?]["\')’”]?$')


# ─────────────────────────────────────────────────────────────
# Timestamp formatting (SRT-style HH:MM:SS,mmm)
# ─────────────────────────────────────────────────────────────

def format_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    whole = int(seconds)
    ms = round((seconds - whole) * 1000)
    if ms == 1000:
        whole += 1
        ms = 0
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_timestamp(value: str) -> float:
    m = re.match(r'^(\d+):(\d{2}):(\d{2}),(\d{3})$', value.strip())
    if not m:
        raise ValueError(f"Not a valid HH:MM:SS,mmm timestamp: {value!r}")
    h, mi, s, ms = (int(x) for x in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000


# ─────────────────────────────────────────────────────────────
# subtitle.md parsing / serialization
#
# SCENE N
#
# Start: 00:00:00,000
# End: 00:00:03,400
# Text: You bought it. You paid for it.
# ---
# Start: 00:00:03,400
# End: 00:00:06,800
# Text: It's yours.
# ─────────────────────────────────────────────────────────────

_LABEL_RE = re.compile(r'^(Start|End|Text):\s*(.*)$', re.IGNORECASE)
_SCENE_HEADER_RE = re.compile(r'^SCENE\s+(\d+)$')


def parse_subtitles(text: str) -> list[Caption]:
    captions: list[Caption] = []
    current_scene: Optional[int] = None
    current_fields: dict = {}
    current_label: Optional[str] = None
    current_lines: list[str] = []

    def flush_field():
        nonlocal current_label, current_lines
        if current_label is not None:
            current_fields[current_label] = "\n".join(current_lines).strip()
        current_label = None
        current_lines = []

    def flush_caption():
        flush_field()
        if current_scene is not None and current_fields.get("text"):
            captions.append({
                "scene_id": current_scene,
                "start_sec": parse_timestamp(current_fields.get("start", "00:00:00,000")),
                "end_sec": parse_timestamp(current_fields.get("end", "00:00:00,000")),
                "text": current_fields["text"],
            })
        current_fields.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        scene_match = _SCENE_HEADER_RE.match(line)
        if scene_match:
            flush_caption()
            current_scene = int(scene_match.group(1))
            continue
        if line == "---":
            flush_caption()
            continue
        label_match = _LABEL_RE.match(line)
        if label_match:
            flush_field()
            current_label = label_match.group(1).lower()
            inline = label_match.group(2).strip()
            current_lines = [inline] if inline else []
        elif current_label is not None:
            current_lines.append(raw_line)

    flush_caption()
    return captions


def serialize_subtitles(captions: list[Caption]) -> str:
    parts: list[str] = []
    current_scene: Optional[int] = None
    scene_lines: list[str] = []

    def flush_scene():
        if current_scene is not None:
            parts.append(f"SCENE {current_scene}\n\n" + "\n---\n".join(scene_lines))

    for caption in captions:
        if caption["scene_id"] != current_scene:
            flush_scene()
            current_scene = caption["scene_id"]
            scene_lines = []
        scene_lines.append(
            f"Start: {format_timestamp(caption['start_sec'])}\n"
            f"End: {format_timestamp(caption['end_sec'])}\n"
            f"Text: {caption['text']}"
        )

    flush_scene()
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Scene text extraction from narration_script.txt's REFERENCE VERSION
# (used only by the pause-heuristic fallback path — the alignment path
# doesn't need scene text, it gets scene boundaries from narration_timing.json)
# ─────────────────────────────────────────────────────────────

_SCENE_BLOCK_RE = re.compile(r'^\[SCENE\s+(\d+)\]$')
_COMMENT_RE = re.compile(r'^<!--.*-->$')
_BREAK_TAG_RE = re.compile(r'<break[^>]*/>', re.IGNORECASE)


def extract_scene_texts(narration_script_text: str) -> dict[int, str]:
    """Parse [SCENE N] blocks out of the REFERENCE VERSION section, stripping
    tone comments (<!-- ... -->) and <break .../> pacing tags, leaving just
    the plain spoken sentences per scene."""
    reference_text = narration_script_text
    if "=== ELEVENLABS VERSION ===" in reference_text:
        reference_text = reference_text.split("=== ELEVENLABS VERSION ===", 1)[0]

    scenes: dict[int, str] = {}
    current_scene: Optional[int] = None
    current_lines: list[str] = []

    def flush():
        if current_scene is not None:
            scenes[current_scene] = "\n".join(current_lines).strip()

    for raw_line in reference_text.splitlines():
        line = raw_line.strip()
        scene_match = _SCENE_BLOCK_RE.match(line)
        if scene_match:
            flush()
            current_scene = int(scene_match.group(1))
            current_lines = []
            continue
        if current_scene is None or not line or _COMMENT_RE.match(line):
            continue
        cleaned = _BREAK_TAG_RE.sub('', line).strip()
        if cleaned:
            current_lines.append(cleaned)

    flush()
    return scenes


# ─────────────────────────────────────────────────────────────
# Shared: packing words into caption-sized, line-wrapped chunks
# ─────────────────────────────────────────────────────────────

def _words_from_text(text: str, start_sec: float, end_sec: float) -> list[WordTiming]:
    """Split plain text into words, distributing [start_sec, end_sec] evenly
    across them by character count — used by the fallback path, which only
    has a time window per text segment, not per-word timing."""
    tokens = text.split()
    if not tokens:
        return []
    total_chars = sum(len(t) for t in tokens) or 1
    duration = max(end_sec - start_sec, 0.0)

    words: list[WordTiming] = []
    cursor = start_sec
    for tok in tokens:
        share = len(tok) / total_chars * duration
        words.append({"text": tok, "start": cursor, "end": cursor + share})
        cursor += share
    return words


def wrap_caption_text(text: str, max_chars_per_line: int = MAX_CHARS_PER_LINE, max_lines: int = MAX_LINES) -> str:
    """Greedy word-wrap into at most max_lines lines of <= max_chars_per_line
    each. Packing already bounds total length, so overflow on the last line
    is a rare edge case, not the common case."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars_per_line and current:
            lines.append(current)
            if len(lines) == max_lines - 1:
                # Last allowed line: let the rest run on rather than drop words.
                current = " ".join(words[i:])
                break
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines[:max_lines])


def pack_words_into_chunks(words: list[WordTiming]) -> list[tuple[float, float, str]]:
    """Greedily pack word timings into caption-sized (start, end, text)
    chunks: caps total length at MAX_CHARS_PER_CAPTION, prefers to end a
    chunk at a sentence boundary once it's carrying a reasonable amount of
    text (avoids tiny one-word captions ending on every period)."""
    chunks: list[tuple[float, float, str]] = []
    current: list[WordTiming] = []
    current_len = 0

    def flush():
        nonlocal current, current_len
        if current:
            text = wrap_caption_text(" ".join(w["text"] for w in current))
            chunks.append((current[0]["start"], current[-1]["end"], text))
        current = []
        current_len = 0

    for word in words:
        added_len = len(word["text"]) + (1 if current else 0)
        if current and current_len + added_len > MAX_CHARS_PER_CAPTION:
            flush()
            added_len = len(word["text"])
        current.append(word)
        current_len += added_len
        if SENTENCE_END_RE.search(word["text"]) and current_len >= MAX_CHARS_PER_CAPTION * 0.4:
            flush()

    flush()
    return chunks


def clamp_caption_durations(
    captions: list[Caption], min_sec: float = MIN_DURATION_SEC, max_sec: float = MAX_DURATION_SEC
) -> list[Caption]:
    """Merge adjacent same-scene captions shorter than min_sec into their
    neighbor, and split any caption longer than max_sec into roughly equal,
    word-boundary-respecting sub-captions."""
    # Merge short captions forward into the next one in the same scene.
    merged: list[Caption] = []
    for cap in captions:
        if (
            merged
            and merged[-1]["scene_id"] == cap["scene_id"]
            and merged[-1]["end_sec"] - merged[-1]["start_sec"] < min_sec
        ):
            prev = merged[-1]
            merged[-1] = {
                "scene_id": prev["scene_id"],
                "start_sec": prev["start_sec"],
                "end_sec": cap["end_sec"],
                "text": wrap_caption_text(f"{prev['text'].replace(chr(10), ' ')} {cap['text'].replace(chr(10), ' ')}"),
            }
        else:
            merged.append(dict(cap))  # type: ignore[arg-type]

    # Split overlong captions.
    result: list[Caption] = []
    for cap in merged:
        duration = cap["end_sec"] - cap["start_sec"]
        if duration <= max_sec:
            result.append(cap)
            continue
        words = cap["text"].replace("\n", " ").split()
        n_parts = min(max(2, int(duration // max_sec) + 1), len(words))
        # Exactly n_parts balanced groups (sizes differ by at most one word) —
        # a fixed stride (len(words) // n_parts) can leave a tiny, too-short
        # trailing remainder group instead of folding it into the last part.
        base_size, remainder = divmod(len(words), n_parts)
        i = 0
        for p in range(n_parts):
            size = base_size + (1 if p < remainder else 0)
            part_words = words[i:i + size]
            if not part_words:
                continue
            frac_start = i / len(words)
            frac_end = min(1.0, (i + len(part_words)) / len(words))
            result.append({
                "scene_id": cap["scene_id"],
                "start_sec": cap["start_sec"] + frac_start * duration,
                "end_sec": cap["start_sec"] + frac_end * duration,
                "text": wrap_caption_text(" ".join(part_words)),
            })
            i += size

    return result


def _scene_id_for_time(narration_timing: dict, t: float) -> int:
    scenes = narration_timing.get("scenes", [])
    for scene in scenes:
        if scene["start_sec"] <= t < scene["end_sec"]:
            return scene["scene_id"]
    # Fall through: clamp to the first/last scene for boundary rounding.
    if scenes and t < scenes[0]["start_sec"]:
        return scenes[0]["scene_id"]
    if scenes:
        return scenes[-1]["scene_id"]
    return 1


# ─────────────────────────────────────────────────────────────
# Primary path: ElevenLabs character-level alignment
# ─────────────────────────────────────────────────────────────

_SSML_TAG_RE = re.compile(r'<[^>]*>')


def chunk_from_alignment(alignment: dict, narration_timing: dict) -> list[Caption]:
    """Build captions from ElevenLabs' /with-timestamps character alignment.
    Scene boundaries come from narration_timing.json (computed independently
    via audio silence detection), not from the alignment text itself — the
    ElevenLabs input text has no [SCENE N] markers and its <break> tags don't
    map 1:1 to scene boundaries, so cross-referencing by time against
    narration_timing's scenes is the reliable approach."""
    characters = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    # The TTS input text carries <break time="1.5s"/>-style pacing tags
    # (spanning multiple whitespace-separated tokens, e.g. "<break" +
    # 'time="1.5s"/>'), which aren't spoken words. Whichever TTS backend's
    # alignment response this came from, defensively exclude any character
    # that falls inside a tag span before grouping into words — otherwise
    # literal tag text can end up baked into a caption.
    full_text = "".join(characters)
    excluded = [False] * len(characters)
    for m in _SSML_TAG_RE.finditer(full_text):
        for i in range(m.start(), m.end()):
            excluded[i] = True

    # Group characters into words on whitespace.
    words: list[WordTiming] = []
    buf_chars: list[str] = []
    buf_start: Optional[float] = None
    buf_end: Optional[float] = None

    def flush_word():
        nonlocal buf_chars, buf_start, buf_end
        if buf_chars:
            words.append({"text": "".join(buf_chars), "start": buf_start or 0.0, "end": buf_end or 0.0})
        buf_chars = []
        buf_start = None
        buf_end = None

    for i, (ch, s, e) in enumerate(zip(characters, starts, ends)):
        if excluded[i] or ch.isspace():
            flush_word()
            continue
        if buf_start is None:
            buf_start = s
        buf_end = e
        buf_chars.append(ch)
    flush_word()

    if not words:
        return []

    chunks = pack_words_into_chunks(words)
    captions: list[Caption] = [
        {
            "scene_id": _scene_id_for_time(narration_timing, (start + end) / 2),
            "start_sec": start,
            "end_sec": end,
            "text": text,
        }
        for start, end, text in chunks
    ]
    return clamp_caption_durations(captions)


# ─────────────────────────────────────────────────────────────
# Fallback path: narration_timing.json's scene-level timing + internal pauses
# ─────────────────────────────────────────────────────────────

def chunk_from_scene_timing(narration_timing: dict, scene_texts: dict[int, str]) -> list[Caption]:
    """Build captions using only the coarse per-scene timing + internal
    pauses already computed by analyze_timing.py — used when no character
    alignment is available (OpenRouter TTS, or a pre-existing run from
    before this feature)."""
    captions: list[Caption] = []

    for scene in narration_timing.get("scenes", []):
        scene_id = scene["scene_id"]
        text = scene_texts.get(scene_id, "")
        if not text:
            continue

        pauses = sorted(scene.get("internal_pauses", []), key=lambda p: p["start"])
        boundaries = [scene["start_sec"]] + [
            (p["start"] + p["end"]) / 2 for p in pauses
        ] + [scene["end_sec"]]

        n_chunks = len(boundaries) - 1
        words_all = text.split()
        if not words_all:
            continue
        per_chunk = max(1, len(words_all) // n_chunks)

        word_groups: list[list[str]] = []
        for i in range(0, len(words_all), per_chunk):
            word_groups.append(words_all[i:i + per_chunk])
        # Merge any overflow group (more groups than boundaries allow) into the last.
        while len(word_groups) > n_chunks:
            word_groups[-2].extend(word_groups.pop())

        for i, group in enumerate(word_groups):
            if not group:
                continue
            start_sec = boundaries[i]
            end_sec = boundaries[i + 1] if i + 1 < len(boundaries) else scene["end_sec"]
            words = _words_from_text(" ".join(group), start_sec, end_sec)
            for chunk_start, chunk_end, chunk_text in pack_words_into_chunks(words):
                captions.append({
                    "scene_id": scene_id,
                    "start_sec": chunk_start,
                    "end_sec": chunk_end,
                    "text": chunk_text,
                })

    return clamp_caption_durations(captions)
