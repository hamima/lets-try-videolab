"""
backend/tests/test_parsers.py — Regression tests for the document parsers in
tasks.py that turn raw LLM output into structured StepContent for the UI.

These parsers were originally written against plain-text output (no markdown
bold around labels). OpenRouter-routed models sometimes wrap field/section
labels in markdown bold (**LABEL:** value), which the original regexes never
matched, silently producing empty sections/scenes/assets in the UI even
though the raw saved file had real content. Fixtures below are drawn from
real captured runs (both formats) to lock in the fix.
"""

import tasks


# ─────────────────────────────────────────────────────────────
# _strip_label_bold
# ─────────────────────────────────────────────────────────────

def test_strip_label_bold_wraps_whole_line():
    assert tasks._strip_label_bold("**VIDEO TITLE**") == "VIDEO TITLE"


def test_strip_label_bold_wraps_label_only():
    assert tasks._strip_label_bold("**ASSET_TYPE:** ai_image") == "ASSET_TYPE: ai_image"


def test_strip_label_bold_noop_on_plain_text():
    assert tasks._strip_label_bold("ASSET_TYPE: ai_image") == "ASSET_TYPE: ai_image"


def test_strip_label_bold_does_not_touch_mid_line_bold():
    # Bulleted content with inline bold should not be mistaken for a label.
    line = "*   **Shein & Temu:** Chinese-founded e-commerce giants."
    assert tasks._strip_label_bold(line) == line


# ─────────────────────────────────────────────────────────────
# _parse_sections (research / story)
# ─────────────────────────────────────────────────────────────

RESEARCH_PLAIN = """\
TOPIC

The De Minimis Loophole: How Shein and Temu Conquered America

VIRALITY SCORE

9/10

KEY STAKEHOLDERS

*   **Shein & Temu:** Chinese-founded e-commerce giants using a direct-to-consumer model.
*   **U.S. Consumers:** Primarily young, price-sensitive shoppers.
"""

STORY_BOLD = """\
**VIDEO TITLE**
How Your Cheap T-Shirt Is Cheating America

**THUMBNAIL TEXT**
THE $800 SECRET SHEIN DOESN'T WANT YOU TO KNOW

**OPENING HOOK**
(Visual: Quick cuts of a user scrolling the Temu app.)
"""


def test_parse_sections_plain_headers():
    sections = tasks._parse_sections(RESEARCH_PLAIN)
    labels = [s["label"] for s in sections]
    assert labels == ["TOPIC", "VIRALITY SCORE", "KEY STAKEHOLDERS"]
    assert "De Minimis Loophole" in sections[0]["content"]
    # Bulleted bold content under a section must stay as content, not a header.
    assert "Shein & Temu" in sections[2]["content"]


def test_parse_sections_bold_headers():
    sections = tasks._parse_sections(STORY_BOLD)
    labels = [s["label"] for s in sections]
    assert labels == ["VIDEO TITLE", "THUMBNAIL TEXT", "OPENING HOOK"]
    assert sections[0]["content"] == "How Your Cheap T-Shirt Is Cheating America"
    assert "THE $800 SECRET" in sections[1]["content"]


def test_parse_sections_bold_headers_not_empty():
    # Regression for the exact reported bug: bold-wrapped headers must not
    # result in zero detected sections.
    sections = tasks._parse_sections(STORY_BOLD)
    assert len(sections) > 0


# ─────────────────────────────────────────────────────────────
# _parse_scene_plan / _parse_beats
# ─────────────────────────────────────────────────────────────

SCENE_PLAN_PLAIN = """\
SCENE 1

Narration:
A top for five dollars. You've seen the prices.

Duration:
20 seconds

Purpose:
VISUAL: shopping app close-up. To hook the viewer with a familiar premise.

Emotion:
Intrigue, curiosity.

---

SCENE 2

Narration:
It starts with a ghost rule, buried in a law from 1930.

Duration:
20 seconds

Purpose:
VISUAL: dusty law book. To provide historical context.

Emotion:
Informative.
"""

SCENE_PLAN_BOLD = """\
SCENE 1

**Narration:**
A top for five dollars. You've seen the prices.

**Duration:**
20 seconds

**Purpose:**
VISUAL: shopping app close-up. To hook the viewer with a familiar premise.

**Emotion:**
Intrigue, curiosity.
"""


def test_parse_scene_plan_plain():
    scenes = tasks._parse_scene_plan(SCENE_PLAN_PLAIN)
    assert [s["id"] for s in scenes] == [1, 2]
    assert len(scenes[0]["beats"]) == 1
    beat = scenes[0]["beats"][0]
    assert beat["narration"].startswith("A top for five dollars")
    assert beat["duration"] == "20 seconds"
    assert beat["visual"] == "shopping app close-up"
    assert beat["emotion"] == "Intrigue, curiosity."


def test_parse_scene_plan_bold_not_empty():
    scenes = tasks._parse_scene_plan(SCENE_PLAN_BOLD)
    assert len(scenes) == 1
    assert len(scenes[0]["beats"]) == 1
    beat = scenes[0]["beats"][0]
    assert beat["narration"].startswith("A top for five dollars")
    assert beat["duration"] == "20 seconds"


# ─────────────────────────────────────────────────────────────
# _parse_asset_manifest_scenes
# ─────────────────────────────────────────────────────────────

ASSET_MANIFEST_PLAIN = """\
Here is the visual asset breakdown for your documentary.

***

### SCENE 1

**1.1**
TYPE: ai_image
KEN_BURNS: zoom_in
VISUAL_GOAL: A glowing ARPANET network diagram
DURATION: 16 seconds
AI_PROMPT: Minimalist illustration of four glowing nodes

**1.2**
TYPE: real_image
KEN_BURNS: zoom_out
VISUAL_GOAL: Vintage teletype terminal
DURATION: 16 seconds
SEARCH_QUERY: ARPANET teletype terminal 1969

---

### SCENE 2

**2.1**
TYPE: ai_image
KEN_BURNS: pan_right
VISUAL_GOAL: Animated map of disconnected network islands
DURATION: 16 seconds
AI_PROMPT: Abstract digital illustration of isolated network clusters
"""

# Real excerpt (reformatted scene count) from a bold-format OpenRouter run —
# this is the exact shape that produced blank scenes before the fix.
ASSET_MANIFEST_BOLD = """\
Here is the visual asset breakdown for your documentary.

---

### SCENE 1

**ASSET_TYPE:** ai_image
**VISUAL_GOAL:** To juxtapose a common, cheap item with the overwhelming scale of the shipping operation it represents.
**AI_PROMPT:** "Macro close-up, slick commercial lighting, a single vibrant red t-shirt."
**KEN_BURNS:** zoom_in
**PRIORITY:** Critical
**DURATION:** 20 seconds

---

### SCENE 2

**ASSET_TYPE:** chart
**VISUAL_GOAL:** A clean, animated graphic visually explaining the loophole.
**AI_PROMPT:** N/A
**KEN_BURNS:** N/A
**STOCK_QUERIES:** N/A (This will be created by a motion graphics artist)
**PRIORITY:** Critical
**DURATION:** 20 seconds
"""


def test_parse_asset_manifest_plain_with_explicit_sub_ids():
    scenes = tasks._parse_asset_manifest_scenes(ASSET_MANIFEST_PLAIN)
    assert [s["id"] for s in scenes] == [1, 2]
    assert [a["id"] for a in scenes[0]["assets"]] == ["1.1", "1.2"]
    fields = {f["label"]: f["content"] for f in scenes[0]["assets"][0]["fields"]}
    assert fields["TYPE"] == "ai_image"
    assert fields["KEN_BURNS"] == "zoom_in"


def test_parse_asset_manifest_bold_not_blank():
    # Regression for the exact reported bug: "asset manifest shows all blank
    # for all scenes" when the model bold-wraps field labels.
    scenes = tasks._parse_asset_manifest_scenes(ASSET_MANIFEST_BOLD)
    assert len(scenes) == 2
    for scene in scenes:
        assert len(scene["assets"]) == 1, f"scene {scene['id']} has no assets"
        fields = {f["label"]: f["content"] for f in scene["assets"][0]["fields"]}
        assert fields.get("ASSET_TYPE")
        assert fields.get("DURATION") == "20 seconds"

    assert scenes[0]["assets"][0]["fields"][0]["label"] == "ASSET_TYPE"
    fields_scene1 = {f["label"]: f["content"] for f in scenes[0]["assets"][0]["fields"]}
    assert fields_scene1["ASSET_TYPE"] == "ai_image"
    assert fields_scene1["KEN_BURNS"] == "zoom_in"


# ─────────────────────────────────────────────────────────────
# _parse_asset_acquisition
# ─────────────────────────────────────────────────────────────

ASSET_ACQUISITION_PLAIN = """\
SCENE 1
ASSET 1.1
TYPE:
ai_image
VISUAL_GOAL:
A glowing ARPANET network diagram
PRIORITY:
Critical
DURATION:
16 seconds
"""

ASSET_ACQUISITION_BOLD = """\
SCENE 1
ASSET 1.1
**TYPE:**
ai_image
**VISUAL_GOAL:**
A glowing ARPANET network diagram
**PRIORITY:**
Critical
**DURATION:**
16 seconds
"""

# Real excerpt from a run where the model numbers assets as a plain integer
# ("ASSET 1") instead of the dotted scene.asset sub-id ("ASSET 1.1"). The
# original regex only matched the dotted form, so "ASSET 1" was silently
# dropped and every scene ended up with an empty assets list.
ASSET_ACQUISITION_PLAIN_ASSET_ID = """\
SCENE 1
ASSET 1
TYPE: ai_image
VISUAL_GOAL: To visually represent the overwhelming flood of packages.
PRIORITY: Critical
DURATION: 20 seconds
SEARCH_QUERY: N/A

SCENE 2
ASSET 1
TYPE: ai_image
VISUAL_GOAL: To personify the ghost rule as an old, forgotten law.
PRIORITY: Critical
DURATION: 20 seconds
SEARCH_QUERY: N/A
"""


def test_parse_asset_acquisition_plain():
    scenes = tasks._parse_asset_acquisition(ASSET_ACQUISITION_PLAIN)
    assert [s["id"] for s in scenes] == [1]
    assert [a["id"] for a in scenes[0]["assets"]] == ["1.1"]
    fields = {f["label"]: f["content"] for f in scenes[0]["assets"][0]["fields"]}
    assert fields["TYPE"] == "ai_image"
    assert fields["DURATION"] == "16 seconds"


def test_parse_asset_acquisition_bold_not_blank():
    scenes = tasks._parse_asset_acquisition(ASSET_ACQUISITION_BOLD)
    assert len(scenes) == 1
    assert len(scenes[0]["assets"]) == 1
    fields = {f["label"]: f["content"] for f in scenes[0]["assets"][0]["fields"]}
    assert fields["TYPE"] == "ai_image"
    assert fields["DURATION"] == "16 seconds"


def test_parse_asset_acquisition_plain_asset_id_not_blank():
    # Regression: plain "ASSET 1" (no dotted sub-id) must not be dropped.
    scenes = tasks._parse_asset_acquisition(ASSET_ACQUISITION_PLAIN_ASSET_ID)
    assert [s["id"] for s in scenes] == [1, 2]
    for scene in scenes:
        assert len(scene["assets"]) == 1, f"scene {scene['id']} has no assets"
        assert scene["assets"][0]["id"] == "1"
    fields = {f["label"]: f["content"] for f in scenes[0]["assets"][0]["fields"]}
    assert fields["TYPE"] == "ai_image"
    assert fields["DURATION"] == "20 seconds"
