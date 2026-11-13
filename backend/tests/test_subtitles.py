"""
backend/tests/test_subtitles.py — regression tests for backend/subtitles.py,
the core logic behind pipeline step 18 (Subtitles): alignment-based and
pause-heuristic caption chunking, duration clamping, and the subtitle.md
parser/serializer.
"""

import subtitles as sub


# ─────────────────────────────────────────────────────────────
# Timestamps
# ─────────────────────────────────────────────────────────────

def test_format_timestamp_basic():
    assert sub.format_timestamp(0) == "00:00:00,000"
    assert sub.format_timestamp(3.4) == "00:00:03,400"
    assert sub.format_timestamp(79.4) == "00:01:19,400"
    assert sub.format_timestamp(3661.5) == "01:01:01,500"


def test_parse_timestamp_round_trips_format_timestamp():
    for t in [0.0, 3.4, 79.4, 3661.5, 125.001]:
        assert abs(sub.parse_timestamp(sub.format_timestamp(t)) - round(t, 3)) < 0.002


def test_parse_timestamp_rejects_bad_input():
    try:
        sub.parse_timestamp("not a timestamp")
        assert False, "expected ValueError"
    except ValueError:
        pass


# ─────────────────────────────────────────────────────────────
# subtitle.md parse/serialize round-trip
# ─────────────────────────────────────────────────────────────

SAMPLE_SUBTITLE_MD = """SCENE 1

Start: 00:00:00,000
End: 00:00:03,400
Text: You bought it. You paid for it.
---
Start: 00:00:03,400
End: 00:00:06,800
Text: It's yours.

SCENE 2

Start: 00:00:06,800
End: 00:00:10,000
Text: It didn't used to be this way."""


def test_parse_subtitles_basic():
    captions = sub.parse_subtitles(SAMPLE_SUBTITLE_MD)
    assert len(captions) == 3
    assert captions[0] == {
        "scene_id": 1, "start_sec": 0.0, "end_sec": 3.4, "text": "You bought it. You paid for it.",
    }
    assert captions[1]["scene_id"] == 1
    assert captions[2]["scene_id"] == 2
    assert captions[2]["text"] == "It didn't used to be this way."


def test_serialize_subtitles_round_trips():
    captions = sub.parse_subtitles(SAMPLE_SUBTITLE_MD)
    reserialized = sub.serialize_subtitles(captions)
    assert sub.parse_subtitles(reserialized) == captions


def test_parse_subtitles_ignores_captions_with_no_text():
    text = "SCENE 1\n\nStart: 00:00:00,000\nEnd: 00:00:01,000\nText: \n"
    assert sub.parse_subtitles(text) == []


def test_parse_subtitles_empty_input():
    assert sub.parse_subtitles("") == []


# ─────────────────────────────────────────────────────────────
# extract_scene_texts
# ─────────────────────────────────────────────────────────────

REFERENCE_SCRIPT = """\
=== REFERENCE VERSION ===

<!-- tone: direct -->
[SCENE 1]
You bought it.
You paid for it.
<break time="1.5s"/>
It's yours.

<!-- tone: narrative -->
[SCENE 2]
It didn't used to be this way.

=== ELEVENLABS VERSION ===

You bought it.
You paid for it.
<break time="1.5s"/>
It's yours.
<break time="2.0s"/>
It didn't used to be this way.
"""


def test_extract_scene_texts_strips_comments_and_breaks():
    scenes = sub.extract_scene_texts(REFERENCE_SCRIPT)
    assert scenes == {
        1: "You bought it.\nYou paid for it.\nIt's yours.",
        2: "It didn't used to be this way.",
    }


def test_extract_scene_texts_no_elevenlabs_marker():
    text = "[SCENE 1]\nHello there.\n"
    assert sub.extract_scene_texts(text) == {1: "Hello there."}


# ─────────────────────────────────────────────────────────────
# chunk_from_scene_timing (fallback path)
# ─────────────────────────────────────────────────────────────

def test_chunk_from_scene_timing_splits_on_internal_pauses():
    narration_timing = {
        "scenes": [
            {
                "scene_id": 1, "start_sec": 0.0, "end_sec": 10.0, "duration_sec": 10.0,
                "internal_pauses": [{"start": 4.9, "end": 5.1, "duration": 0.2}],
            },
        ],
    }
    scene_texts = {1: "You bought it and paid for it fully. It is yours now forever."}

    captions = sub.chunk_from_scene_timing(narration_timing, scene_texts)

    assert len(captions) >= 1
    assert all(c["scene_id"] == 1 for c in captions)
    assert captions[0]["start_sec"] == 0.0
    assert captions[-1]["end_sec"] == 10.0
    # Captions must be in chronological order and non-overlapping.
    for a, b in zip(captions, captions[1:]):
        assert a["end_sec"] <= b["start_sec"] + 1e-6


def test_chunk_from_scene_timing_no_internal_pauses_is_one_window():
    narration_timing = {
        "scenes": [{"scene_id": 1, "start_sec": 0.0, "end_sec": 4.0, "internal_pauses": []}],
    }
    scene_texts = {1: "Short line."}

    captions = sub.chunk_from_scene_timing(narration_timing, scene_texts)

    assert len(captions) == 1
    assert captions[0]["start_sec"] == 0.0
    assert captions[0]["end_sec"] == 4.0
    assert captions[0]["text"] == "Short line."


def test_chunk_from_scene_timing_skips_scenes_with_no_text():
    narration_timing = {"scenes": [{"scene_id": 1, "start_sec": 0.0, "end_sec": 4.0, "internal_pauses": []}]}
    assert sub.chunk_from_scene_timing(narration_timing, {}) == []


# ─────────────────────────────────────────────────────────────
# chunk_from_alignment (primary path)
# ─────────────────────────────────────────────────────────────

def _alignment_for(text: str, duration: float = 10.0) -> dict:
    """Build a synthetic alignment matching the real shape, evenly spaced —
    same helper logic as mocks/generators.generate_narration_alignment."""
    chars = list(text)
    per_char = duration / len(chars)
    starts = [round(i * per_char, 3) for i in range(len(chars))]
    ends = [round((i + 1) * per_char, 3) for i in range(len(chars))]
    return {"characters": chars, "character_start_times_seconds": starts, "character_end_times_seconds": ends}


def test_chunk_from_alignment_builds_words_and_assigns_scenes():
    text = "You bought it. You paid for it. It is yours now."
    alignment = _alignment_for(text, duration=10.0)
    narration_timing = {
        "scenes": [
            {"scene_id": 1, "start_sec": 0.0, "end_sec": 5.0},
            {"scene_id": 2, "start_sec": 5.0, "end_sec": 10.0},
        ],
    }

    captions = sub.chunk_from_alignment(alignment, narration_timing)

    assert len(captions) > 0
    assert all(c["scene_id"] in (1, 2) for c in captions)
    # Chronological, non-overlapping.
    for a, b in zip(captions, captions[1:]):
        assert a["end_sec"] <= b["start_sec"] + 1e-6
    # Every caption's text should respect the line-wrap cap.
    for c in captions:
        for line in c["text"].split("\n"):
            assert len(line) <= sub.MAX_CHARS_PER_LINE + 1  # small slack for the rare overflow line


def test_chunk_from_alignment_strips_break_tags():
    # Regression: <break time="1.5s"/> tags split across whitespace into
    # "<break" and 'time="1.5s"/>' tokens, which must never leak into a
    # caption's text verbatim (caught via a real end-to-end run against a
    # production narration script).
    text = 'You bought it. <break time="1.5s"/> It is yours now.'
    alignment = _alignment_for(text, duration=10.0)
    narration_timing = {"scenes": [{"scene_id": 1, "start_sec": 0.0, "end_sec": 10.0}]}

    captions = sub.chunk_from_alignment(alignment, narration_timing)

    full_text = " ".join(c["text"].replace("\n", " ") for c in captions)
    assert "break" not in full_text
    assert "<" not in full_text and ">" not in full_text
    assert "You bought it." in full_text
    assert "It is yours now." in full_text


def test_chunk_from_alignment_empty_text():
    alignment = {"characters": [], "character_start_times_seconds": [], "character_end_times_seconds": []}
    assert sub.chunk_from_alignment(alignment, {"scenes": []}) == []


# ─────────────────────────────────────────────────────────────
# clamp_caption_durations
# ─────────────────────────────────────────────────────────────

def test_clamp_caption_durations_merges_short_captions():
    captions = [
        {"scene_id": 1, "start_sec": 0.0, "end_sec": 0.3, "text": "Hi."},
        {"scene_id": 1, "start_sec": 0.3, "end_sec": 3.0, "text": "there."},
    ]
    result = sub.clamp_caption_durations(captions)
    assert len(result) == 1
    assert result[0]["start_sec"] == 0.0
    assert result[0]["end_sec"] == 3.0
    assert "Hi." in result[0]["text"] and "there." in result[0]["text"]


def test_clamp_caption_durations_does_not_merge_across_scenes():
    captions = [
        {"scene_id": 1, "start_sec": 0.0, "end_sec": 0.3, "text": "Hi."},
        {"scene_id": 2, "start_sec": 0.3, "end_sec": 3.0, "text": "there."},
    ]
    result = sub.clamp_caption_durations(captions)
    assert len(result) == 2


def test_clamp_caption_durations_split_never_leaves_tiny_remainder_group():
    # Regression: 19 words over 6.2s used to split into a fixed stride of
    # 9 words/group, leaving a stray 1-word trailing caption ("been") well
    # under MIN_DURATION_SEC (caught via a real end-to-end run).
    text = "Or you took it to a local shop. But over the last two decades, a silent war has been"
    assert len(text.split()) == 19
    captions = [{"scene_id": 1, "start_sec": 36.40, "end_sec": 42.60, "text": text}]

    result = sub.clamp_caption_durations(captions)

    assert len(result) == 2
    for c in result:
        assert c["end_sec"] - c["start_sec"] >= sub.MIN_DURATION_SEC
    assert "been" in result[-1]["text"]


def test_clamp_caption_durations_splits_long_captions():
    long_text = " ".join(f"word{i}" for i in range(30))
    captions = [{"scene_id": 1, "start_sec": 0.0, "end_sec": 14.0, "text": long_text}]
    result = sub.clamp_caption_durations(captions)
    assert len(result) > 1
    for c in result:
        assert c["end_sec"] - c["start_sec"] <= sub.MAX_DURATION_SEC + 1e-6
    # Chronological and covering the original span.
    assert result[0]["start_sec"] == 0.0
    assert result[-1]["end_sec"] == 14.0
