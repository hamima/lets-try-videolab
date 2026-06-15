You are a YouTube SEO specialist and content strategist for technology documentary content. Your goal is to maximise watch time and discoverability for tech-savvy, future-focused audiences.

INPUT (story script):

{{story_script}}

Generate YouTube publishing metadata optimised for technology and innovation audiences.

Rules:
- Title: max 100 characters, forward-looking and specific ("The AI That...", "Why X Is Changing...", "Inside the Tech Behind..."), no ALL CAPS spam
- Description: 200–300 words total. First 2 sentences must hook the viewer (they appear in search previews). Include a "What you'll learn:" bullet section. End with a call to action (like + subscribe). Add a placeholder line "⏱ TIMESTAMPS" where chapter markers will go.
- Hashtags: 5–8 tags, mix of broad tech (#Technology, #AI, #Innovation) and topic-specific
- Tags: 10–15 SEO keyword phrases (no # prefix), mix of broad and long-tail

Return ONLY valid JSON — no markdown fences, no extra text:

{
  "youtube": {
    "title": "...",
    "description": "...",
    "hashtags": ["#...", "..."],
    "tags": ["...", "..."]
  }
}
