import { http, HttpResponse, delay } from 'msw'

// ─────────────────────────────────────────────────────────────────────────────
// Inference mock state
// ─────────────────────────────────────────────────────────────────────────────

const inferencePollCounts: Record<string, number> = {}

// ─────────────────────────────────────────────────────────────────────────────
// Step metadata
// ─────────────────────────────────────────────────────────────────────────────

const STEP_NAMES: Record<string, string> = {
  '1': 'Research', '2': 'Story Script', '3': 'Scene Breakdown',
  '4': 'Asset Manifest', '5': 'Asset Acquisition Instructions',
  '6': 'Fetch Assets', '7': 'AI Image Generation', '8': 'Animation Prompt',
  '9': 'Video Animation', '10': 'Narration Script', '11': 'Narration Audio',
  '12': 'Music Prompt', '13': 'Music Audio', '14': 'Asset Inventory',
  '15': 'Narration Timing', '16': 'Edit Decision List', '17': 'Final Assembly',
  '18': 'Platform Metadata',
}

const STEP_TYPES: Record<string, string> = {
  '1': 'gemini', '2': 'gemini', '3': 'gemini', '4': 'gemini', '5': 'gemini',
  '6': 'fetch_assets', '7': 'imagen', '8': 'animation_prompt',
  '9': 'runpod_animation', '10': 'gemini', '11': 'tts', '12': 'gemini',
  '13': 'music', '14': 'script', '15': 'script', '16': 'gemini',
  '17': 'script', '18': 'gemini',
}

// ─────────────────────────────────────────────────────────────────────────────
// Mutable run state — single source of truth for both list and detail endpoints
// ─────────────────────────────────────────────────────────────────────────────

interface RunState {
  domain: string
  run_id: string
  workspace: string
  created_at: string
  steps_completed: number
  steps_failed: number
  steps_total: number
  videos: string[]
  // Active run tracking
  active: boolean
  active_step: string | null
  start_step: number       // which step index it started active from
  start_time: number       // ms timestamp when active run started
  ms_per_step: number      // how fast to advance (ms per step)
  max_step: number         // stop progressing after this step (18 = full run, 1 = preview)
  failed_steps: string[]   // specific step IDs that failed
}

// Each step advances every 8s in mock mode (fast enough to see in dev)
const INITIAL_RUNS: RunState[] = [
  {
    domain: 'political',
    run_id: '2026-08-20_143022',
    workspace: 'workspace/political/2026-08-20_143022',
    created_at: '2026-08-20T14:30:22',
    active: true,
    active_step: '8',
    start_step: 7,
    start_time: Date.now() - 3000,
    ms_per_step: 8000,
    max_step: 18,
    steps_completed: 7,
    steps_failed: 0,
    steps_total: 18,
    videos: [],
    failed_steps: [],
  },
  {
    domain: 'science',
    run_id: '2026-08-19_091544',
    workspace: 'workspace/science/2026-08-19_091544',
    created_at: '2026-08-19T09:15:44',
    active: false,
    active_step: null,
    start_step: 18,
    start_time: 0,
    ms_per_step: 8000,
    max_step: 18,
    steps_completed: 18,
    steps_failed: 0,
    steps_total: 18,
    videos: [
      'workspace/science/2026-08-19_091544/assets/scene_1/asset_1/animated.mp4',
      'workspace/science/2026-08-19_091544/assets/scene_2/asset_1/animated.mp4',
      'workspace/science/2026-08-19_091544/assets/scene_3/asset_1/animated.mp4',
    ],
    failed_steps: [],
  },
  {
    domain: 'technology',
    run_id: '2026-08-18_162233',
    workspace: 'workspace/technology/2026-08-18_162233',
    created_at: '2026-08-18T16:22:33',
    active: false,
    active_step: null,
    start_step: 5,
    start_time: 0,
    ms_per_step: 8000,
    max_step: 18,
    steps_completed: 5,
    steps_failed: 2,
    steps_total: 18,
    videos: [],
    failed_steps: ['6', '7'],
  },
]

// Keyed by "domain/run_id" for fast lookup
const runStore: Record<string, RunState> = {}
for (const r of INITIAL_RUNS) runStore[`${r.domain}/${r.run_id}`] = r

// ─────────────────────────────────────────────────────────────────────────────
// Progression helper — time-based so list and detail always agree
// ─────────────────────────────────────────────────────────────────────────────

function resolveRun(r: RunState): { completed: number; activeStep: string | null; active: boolean } {
  if (!r.active) return { completed: r.steps_completed, activeStep: null, active: false }

  const elapsed = Date.now() - r.start_time
  const stepsAdvanced = Math.floor(elapsed / r.ms_per_step)
  const completed = Math.min(r.max_step, r.start_step + stepsAdvanced)
  const active = completed < r.max_step
  const activeStep = active ? String(completed + 1) : null
  return { completed, activeStep, active }
}

function buildStepList(r: RunState) {
  const { completed, activeStep } = resolveRun(r)
  return Array.from({ length: 18 }, (_, i) => {
    const id = String(i + 1)
    const n = i + 1
    let status: 'pending' | 'running' | 'done' | 'failed' = 'pending'
    if (r.failed_steps.includes(id)) status = 'failed'
    else if (id === activeStep) status = 'running'
    else if (n <= completed) status = 'done'
    return { id, name: STEP_NAMES[id], type: STEP_TYPES[id], status }
  })
}

function toSummary(r: RunState) {
  const { completed, activeStep, active } = resolveRun(r)
  return {
    domain: r.domain,
    run_id: r.run_id,
    workspace: r.workspace,
    created_at: r.created_at,
    active,
    active_step: activeStep,
    steps_completed: completed,
    steps_failed: r.failed_steps.length,
    steps_total: 18,
    videos: r.videos,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Rerun tracking — a rerun step spends 6s in "running" then becomes "done"
// ─────────────────────────────────────────────────────────────────────────────

interface RerunEntry { domain: string; runId: string; stepId: string; startedAt: number }
const reruns: RerunEntry[] = []
const RERUN_DURATION_MS = 6000

function getRerunStatus(domain: string, runId: string, stepId: string): 'running' | 'done' | null {
  const entry = reruns.find(e => e.domain === domain && e.runId === runId && e.stepId === stepId)
  if (!entry) return null
  return Date.now() - entry.startedAt < RERUN_DURATION_MS ? 'running' : 'done'
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock content — all 18 steps, two domains with rich data
// ─────────────────────────────────────────────────────────────────────────────

const POLITICAL = 'political'
const SCIENCE   = 'science'
const TECH      = 'technology'

type Content = Record<string, object>

const CONTENT: Record<string, Content> = {
  [POLITICAL]: {
    '1': { kind: 'research', sections: [
      { label: 'TOPIC', content: 'The Crisis of Democratic Trust (2026)' },
      { label: 'One-line summary', content: 'Global trust in governments has hit an all-time low of 28% — the lowest ever recorded — as citizens question whether democratic institutions still serve them.' },
      { label: 'VIRALITY SCORE', content: '9/10' },
      { label: 'WHY THIS STORY MATTERS', content: 'This isn\'t just a political squabble. It\'s a civilisational question: can democracy survive the age of disinformation, inequality, and short-termism? The outcome will define the political reality your children inherit.' },
      { label: 'KEY STAKEHOLDERS', content: '• Citizens across G7 nations\n• Traditional political parties in decline\n• Populist and anti-establishment movements\n• Tech platforms amplifying division\n• Citizens\' assembly organisers and civic reformers' },
      { label: 'TIMELINE OF EVENTS', content: '• 2015: Financial crisis aftermath — trust collapses in Southern Europe\n• 2016–2020: Brexit, Trump, global populist surge\n• 2023: Governance scandals across 12+ OECD nations\n• 2026: Trust index reaches record low of 28% globally' },
      { label: 'MAIN FACTS', content: '1. Global average trust in governments: 28% (Edelman 2026)\n2. Voter turnout decline in OECD nations: −14% since 2018\n3. Active protest participants worldwide: 510 million (2026)' },
      { label: 'CONTROVERSIES', content: '• Is this a temporary crisis or a permanent structural shift?\n• Are citizens disengaged or simply migrating to new forms of civic participation?\n• Do citizens\' assemblies scale, or are they an elite experiment?' },
      { label: 'POTENTIAL VIDEO TITLES', content: '1. Who Does Democracy Actually Serve?\n2. The Year Citizens Stopped Trusting Everyone\n3. Is Democracy Broken — Or Just Changing?\n4. Why 72% of the World No Longer Trusts Its Government' },
    ]},
    '1_old': { kind: 'markdown', content: `# Research Dossier — The Crisis of Democratic Trust (2026)

## Executive Summary

The political landscape of 2026 is defined by three converging crises that are reshaping the relationship between citizens and their governments:

1. **Institutional distrust at record highs** — Global average trust in national governments has fallen to 28%, the lowest level since Edelman began tracking in 2001.
2. **The information war** — Synthetic media has made it nearly impossible to distinguish authentic political events from fabrications without third-party verification.
3. **Economic divergence** — The gap between top-decile and median household wealth has doubled in G7 nations since 2018.

## Key Data Points

| Metric | 2018 | 2022 | 2026 |
|--------|------|------|------|
| Trust in government (global avg) | 47% | 35% | 28% |
| Voter turnout decline (OECD avg) | −3% | −8% | −14% |
| Active protest participants (millions) | 120 | 280 | 510 |

## Primary Sources

- Edelman Trust Barometer 2026
- Pew Research Center: Political Polarisation Survey Q1 2026
- World Economic Forum: Global Risks Report 2026
- Reuters Investigates: The New Populism (March 2026)` },

    '2': { kind: 'story', sections: [
      { label: 'VIDEO TITLE', content: 'The Collapse of Trust' },
      { label: 'THUMBNAIL TEXT', content: 'WHY NOBODY BELIEVES ANYONE ANYMORE' },
      { label: 'OPENING HOOK', content: '(VISUAL: Drone shot descending into a vast protest crowd, golden hour.)\n\nNarrator: In the spring of 2026, something unprecedented happened. Not in one country — but simultaneously, across dozens of nations. Citizens reached the same conclusion: the institutions built to represent them had stopped listening.' },
      { label: 'FULL NARRATION SCRIPT', content: '(0–30 seconds: Hook)\nIn 2026, global trust in governments hit an all-time low. Not in one country — everywhere. This is the story of why.\n\n(30–90 seconds: The Fracture)\nThe financial crisis of 2015 was the first crack. The pandemic failures of 2020 deepened it. Scandal after scandal after 2023 shattered what remained.\n\n(90–150 seconds: The Response)\nBut in the wreckage, something new is growing. Citizens\' assemblies. Cooperative platforms. A generation building democracy from scratch.\n\n(150–180 seconds: The Question)\nThe question is whether these experiments can scale fast enough. And whether the old order will allow them to.' },
      { label: 'NARRATIVE ARC', content: 'Act I: The Breaking Point — how trust collapsed\nAct II: The Architecture of Distrust — why it happened\nAct III: What Comes Next — new civic experiments emerging' },
    ]},
    '2_old': { kind: 'markdown', content: `# Story Script — The Collapse of Trust

## Act I: The Breaking Point (0:00–1:30)

In the spring of 2026, something remarkable happened. Not in one country, but simultaneously across dozens. Citizens, separated by oceans and languages, reached the same conclusion: the institutions built to represent them had stopped listening.

The footage from Brussels, São Paulo, Jakarta, and Detroit told the same story. People in the streets — not radicals, but teachers, engineers, nurses, retirees — holding signs that asked the same question in different languages: *Who is this system for?*

## Act II: The Architecture of Distrust (1:30–3:00)

To understand the collapse, we need to go back a decade. The financial crisis of 2015, the pandemic failures of 2020, the governance scandals of 2023 — each one chipped away at the foundation. Each broken promise left a hairline fracture. Until, in 2026, the structure finally gave way.

Social media accelerated everything. The same platforms that were supposed to democratise information became accelerants for outrage. Algorithms rewarded division. Nuance was the first casualty.

## Act III: What Comes Next (3:00–4:30)

But this is not a story of despair. In the wreckage of old institutions, new forms of civic life are emerging. Citizen assemblies in Ireland and France are writing climate policy. Cooperative platforms are replacing extractive corporations. A generation that was written off as apathetic is building the infrastructure for a different kind of democracy.

The question is whether these experiments can scale — and whether the old order will allow them to.` },

    '3': { kind: 'scene_plan', scenes: [
      { id: 1, beats: [
        { narration: 'In the spring of 2026, something unprecedented happened.', duration: '6 seconds', visual: 'Aerial drone shot descending slowly into a vast protest crowd, golden evening light', purpose: 'Establish the scale and emotion of global unrest from above', emotion: 'Awe' },
        { narration: 'Not in one country — but simultaneously, across dozens of nations.', duration: '5 seconds', visual: 'Quick cuts: protest signs in English, French, Arabic, Spanish, Portuguese', purpose: 'Convey the global and universal nature of the movement', emotion: 'Urgency' },
        { narration: 'Citizens reached the same conclusion: the institutions built to represent them had stopped listening.', duration: '8 seconds', visual: 'Close-up of a single protester\'s face, determined and calm', purpose: 'Ground the global movement in a single human moment', emotion: 'Resolve' },
      ]},
      { id: 2, beats: [
        { narration: 'The data tells a stark story.', duration: '3 seconds', visual: 'Animated line graph: trust in government declining from 2016 to 2026', purpose: 'Introduce the statistical evidence for the collapse', emotion: 'Clarity' },
        { narration: 'Global trust in governments has fallen to 28% — the lowest ever recorded.', duration: '6 seconds', visual: 'The graph flatlines at 28%, a red line marking "all-time low"', purpose: 'Land the key statistic with visual weight', emotion: 'Impact' },
        { narration: 'In just a decade, the social contract that held modern democracies together began to fray.', duration: '7 seconds', visual: 'Split screen: archival footage of civic pride in the 2010s vs. empty polling stations in 2026', purpose: 'Show the before and after of civic participation', emotion: 'Loss' },
      ]},
      { id: 3, beats: [
        { narration: 'But this is not a story of despair.', duration: '4 seconds', visual: 'Citizens seated in a circular assembly hall, engaged in discussion', purpose: 'Pivot the emotional tone — introduce hope', emotion: 'Hope' },
        { narration: 'In the wreckage of old institutions, new forms of civic life are taking root.', duration: '6 seconds', visual: 'Montage: citizens\' assembly in Dublin, cooperative platform launch in Paris, community vote in a town hall', purpose: 'Show concrete examples of democratic renewal', emotion: 'Possibility' },
      ]},
    ]},
    '3_old': { kind: 'markdown', content: `# Scene Plan — The Collapse of Trust

---
SCENE 1 / ASSET 1
KEN_BURNS: zoom_in
VISUAL_GOAL: Establish scale of global unrest — aerial protest shot
DURATION: 12 seconds
TYPE: ai_image

---
SCENE 1 / ASSET 2
KEN_BURNS: pan_left
VISUAL_GOAL: Close-up of protest signs in multiple languages
DURATION: 6 seconds
TYPE: real_image

---
SCENE 2 / ASSET 1
KEN_BURNS: zoom_out
VISUAL_GOAL: Data visualisation — trust collapse graph over time
DURATION: 8 seconds
TYPE: ai_image

---
SCENE 3 / ASSET 1
KEN_BURNS: pan_right
VISUAL_GOAL: Split screen: old parliament vs. online civic platform
DURATION: 10 seconds
TYPE: ai_image

---
SCENE 4 / ASSET 1
KEN_BURNS: zoom_in
VISUAL_GOAL: Portrait of a citizen activist speaking to camera
DURATION: 9 seconds
TYPE: real_image

---
SCENE 5 / ASSET 1
KEN_BURNS: zoom_out
VISUAL_GOAL: Wide shot of a citizens' assembly in session
DURATION: 11 seconds
TYPE: ai_image` },

    '4': { kind: 'markdown', content: `# Asset Manifest

---
SCENE 1 / ASSET 1
TYPE: ai_image
KEN_BURNS: zoom_in
VISUAL_GOAL: Aerial drone view of massive protest crowd, European capital, golden hour
DURATION: 12 seconds

---
SCENE 1 / ASSET 2
TYPE: real_image
KEN_BURNS: pan_left
VISUAL_GOAL: Close-up protest signs in English, French, Spanish, Arabic
DURATION: 6 seconds

---
SCENE 2 / ASSET 1
TYPE: ai_image
KEN_BURNS: zoom_out
VISUAL_GOAL: Animated line graph showing trust in government declining 2016–2026
DURATION: 8 seconds

---
SCENE 3 / ASSET 1
TYPE: ai_image
KEN_BURNS: pan_right
VISUAL_GOAL: Split-screen: ornate parliament chamber on left, modern collaborative app UI on right
DURATION: 10 seconds

---
SCENE 4 / ASSET 1
TYPE: real_image
KEN_BURNS: zoom_in
VISUAL_GOAL: Activist speaking passionately at outdoor event
DURATION: 9 seconds

---
SCENE 5 / ASSET 1
TYPE: ai_image
KEN_BURNS: zoom_out
VISUAL_GOAL: Citizens seated in circular assembly, deliberating
DURATION: 11 seconds` },

    '5': { kind: 'markdown', content: `# Asset Acquisition Instructions

SCENE 1
ASSET 1
TYPE: ai_image
AI_PROMPT: Aerial drone photograph of an enormous protest crowd filling a grand European city square, thousands of people visible from above, golden hour lighting, protest signs visible from above, photorealistic, 4K quality, cinematic composition

SCENE 1
ASSET 2
TYPE: real_image
SEARCH_QUERY: protest signs multiple languages Europe 2026
SEARCH_VARIATIONS:
1. "protest signs multilingual Europe demonstration"
2. "political protest placards international"

SCENE 2
ASSET 1
TYPE: ai_image
AI_PROMPT: Clean infographic visualisation of a declining line graph showing trust in government from 2016 to 2026, dark background, glowing blue line, percentage labels, photorealistic data art, 4K

SCENE 3
ASSET 1
TYPE: ai_image
AI_PROMPT: Split-screen image: left side shows an ornate 19th century parliament chamber with politicians debating, right side shows a modern collaborative digital platform interface with citizens participating, dramatic contrast, high quality

SCENE 4
ASSET 1
TYPE: real_image
SEARCH_QUERY: citizen activist speaking crowd outdoor rally

SCENE 5
ASSET 1
TYPE: ai_image
AI_PROMPT: Wide-angle photograph of a circular citizens assembly hall, diverse group of people seated in semicircles facing a speaker, democratic deliberation, natural lighting, photorealistic` },

    '6': {
      kind: 'assets_viewer',
      scenes: [
        {
          id: '1',
          assets: [
            { id: '1.1', files: [
              { type: 'image', label: 'Image', filename: 'image.png', url: 'https://picsum.photos/seed/protest1/640/360' },
              { type: 'text',  label: 'AI Prompt', filename: 'generated.txt', content: 'Aerial view of a large protest crowd in a city square, evening golden hour, wide-angle documentary style' },
              { type: 'text',  label: 'Animation Prompt', filename: 'animated.txt', content: 'The camera begins high above the city square, slowly pushing forward and descending toward the mass of protesters below.' },
            ]},
            { id: '1.2', files: [
              { type: 'image', label: 'Image', filename: 'image.jpg', url: 'https://picsum.photos/seed/activist1/640/360' },
              { type: 'text',  label: 'Search Query', filename: 'search_query.txt', content: 'citizen activist speaking crowd outdoor rally' },
            ]},
          ],
        },
        {
          id: '2',
          assets: [
            { id: '2.1', files: [
              { type: 'image', label: 'Image', filename: 'image.png', url: 'https://picsum.photos/seed/graph2/640/360' },
              { type: 'text',  label: 'AI Prompt', filename: 'generated.txt', content: 'Line chart showing voter turnout decline over decades, minimalist data visualisation, dark background' },
              { type: 'text',  label: 'Animation Prompt', filename: 'animated.txt', content: 'The line graph\'s data points materialise one by one, the downward trend drawing itself across the screen.' },
            ]},
          ],
        },
        {
          id: '3',
          assets: [
            { id: '3.1', files: [
              { type: 'image', label: 'Image', filename: 'image.png', url: 'https://picsum.photos/seed/parliament3/640/360' },
              { type: 'text',  label: 'AI Prompt', filename: 'generated.txt', content: 'Split screen: ornate parliament chamber on left, modern digital civic platform on right, photorealistic' },
              { type: 'text',  label: 'Animation Prompt', filename: 'animated.txt', content: 'The split screen composition pans gently rightward, drawing the eye from the static, gilded parliament chamber to the dynamic digital interface.' },
            ]},
          ],
        },
        {
          id: '5',
          assets: [
            { id: '5.1', files: [
              { type: 'image', label: 'Image', filename: 'image.png', url: 'https://picsum.photos/seed/assembly5/640/360' },
              { type: 'text',  label: 'AI Prompt', filename: 'generated.txt', content: 'Circular citizens assembly hall, diverse participants seated in semicircles, democratic deliberation, natural light' },
              { type: 'text',  label: 'Animation Prompt', filename: 'animated.txt', content: 'A slow zoom-out reveals the circular assembly in its entirety. People lean toward each other in conversation.' },
            ]},
          ],
        },
      ],
    },

    '7': {
      kind: 'image_list',
      images: [
        { path: 'assets/scene_1/asset_1/image.png', url: 'https://picsum.photos/seed/protest1/640/360', label: 'scene_1/asset_1' },
        { path: 'assets/scene_2/asset_1/image.png', url: 'https://picsum.photos/seed/graph2/640/360', label: 'scene_2/asset_1' },
        { path: 'assets/scene_3/asset_1/image.png', url: 'https://picsum.photos/seed/parliament3/640/360', label: 'scene_3/asset_1' },
        { path: 'assets/scene_5/asset_1/image.png', url: 'https://picsum.photos/seed/assembly5/640/360', label: 'scene_5/asset_1' },
      ],
    },

    '8': {
      kind: 'animation_list',
      items: [
        { path: 'assets/scene_1/asset_1/animated.txt', label: 'scene_1/asset_1', text: 'The camera begins high above the city square, slowly pushing forward and descending toward the mass of protesters below. Signs sway rhythmically. The crowd breathes like a single organism. Warm evening light catches the upturned faces. A sense of unified purpose and barely contained energy fills the frame.' },
        { path: 'assets/scene_2/asset_1/animated.txt', label: 'scene_2/asset_1', text: 'The line graph\'s data points materialise one by one, the downward trend drawing itself across the screen with a glowing blue trail. Each dip corresponds to a historical crisis. The camera slowly pulls back to reveal the full catastrophic decline. Numbers pulse with quiet urgency.' },
        { path: 'assets/scene_3/asset_1/animated.txt', label: 'scene_3/asset_1', text: 'The split screen composition pans gently rightward, drawing the eye from the static, gilded parliament chamber to the dynamic, participatory digital interface. Citizens on the right side are active, moving, engaged. The contrast tells the story without a word of narration.' },
        { path: 'assets/scene_5/asset_1/animated.txt', label: 'scene_5/asset_1', text: 'A slow zoom-out reveals the circular assembly in its entirety. People lean toward each other in conversation. Hands are raised. A speaker at the centre holds the floor. The democratic energy is palpable. The camera moves with a sense of hopeful curiosity.' },
      ],
    },

    '9': {
      kind: 'video_list',
      videos: [
        { scene_id: '1', asset_id: '1', label: 'scene_1/asset_1', thumbnail_url: 'https://picsum.photos/seed/protest1/640/360', video_url: null, status: 'pending' },
        { scene_id: '2', asset_id: '1', label: 'scene_2/asset_1', thumbnail_url: 'https://picsum.photos/seed/graph2/640/360', video_url: null, status: 'pending' },
        { scene_id: '3', asset_id: '1', label: 'scene_3/asset_1', thumbnail_url: 'https://picsum.photos/seed/parliament3/640/360', video_url: null, status: 'pending' },
        { scene_id: '5', asset_id: '1', label: 'scene_5/asset_1', thumbnail_url: 'https://picsum.photos/seed/assembly5/640/360', video_url: null, status: 'pending' },
      ],
    },

    '10': { kind: 'markdown', content: `# Narration Script — The Collapse of Trust

=== ELEVENLABS VERSION ===

In the spring of twenty twenty six, something unprecedented happened. Not in one country — but simultaneously, across dozens of nations. Citizens reached the same conclusion: the institutions built to represent them had stopped listening.

The data tells a stark story. Global trust in governments has fallen to twenty eight percent — the lowest ever recorded. In just a decade, the social contract that held modern democracies together began to fray.

But this collapse did not happen in a vacuum. It was built, brick by brick, from broken promises. From financial crises that punished workers but rescued banks. From a pandemic that exposed the gaps between official reassurance and lived reality. From scandal after scandal that answered the same unspoken question: who does power actually serve?

The footage from Brussels, São Paulo, Jakarta, and Detroit was strikingly similar. People in the streets — not radicals, but teachers, engineers, nurses, retirees. Asking, in different languages, the same question: who is this system for?

And yet — this is not a story of despair. In the wreckage of old institutions, new forms of civic life are taking root. Citizens' assemblies in Ireland and France are writing climate policy from the ground up. Cooperative platforms are replacing extractive corporations. A generation written off as apathetic is building the infrastructure for a different kind of democracy.

The question now is whether these experiments can scale fast enough. And whether the old order will allow them to.` },

    '11': { kind: 'audio', url: null },

    '12': { kind: 'text', content: `Ambient documentary score for "The Collapse of Trust" — 2026 political crisis documentary.

Style: Cinematic, understated, emotionally resonant. Think Hans Zimmer's "Interstellar" meets Max Richter's "On the Nature of Daylight".

Instrumentation: Primarily strings (cello-led), sparse piano, subtle electronic textures. No percussion initially — introduce light, measured percussion in Act II to build tension.

Emotional arc:
- Opening: Melancholic, slow strings. A sense of something fragile being held together.
- Act I: Building unease. Dissonant piano notes. The strings begin to fracture.
- Act II: Tension peaks. Electronic elements intensify. A feeling of systems failing.
- Act III: Resolution — not triumphant, but hopeful. A single clear piano line emerges from the noise.

Tempo: 60–70 BPM throughout. Never hurried. The weight of history should be felt.
Duration: 3.5 minutes, loopable.` },

    '13': { kind: 'audio', url: null },

    '14': { kind: 'text', content: `ASSET INVENTORY — political/2026-08-20_143022
Generated: 2026-08-20 16:45:11
==================================================

SCENE 1 / ASSET 1
  Type      : ai_image
  File      : assets/scene_1/asset_1/image.png
  Size      : 1.8 MB
  Dimensions: 1920×1080
  Status    : READY

SCENE 1 / ASSET 2
  Type      : real_image
  File      : assets/scene_1/asset_2/image.jpg
  Size      : 842 KB
  Source    : Wikimedia Commons
  Status    : READY

SCENE 2 / ASSET 1
  Type      : ai_image
  File      : assets/scene_2/asset_1/image.png
  Size      : 1.2 MB
  Status    : READY

SCENE 3 / ASSET 1
  Type      : ai_image
  File      : assets/scene_3/asset_1/image.png
  Size      : 2.1 MB
  Status    : READY

SCENE 5 / ASSET 1
  Type      : ai_image
  File      : assets/scene_5/asset_1/image.png
  Size      : 1.6 MB
  Status    : READY

SUMMARY
  Total assets : 5
  Ready        : 5
  Missing      : 0
  Animated     : 4` },

    '15': {
      kind: 'json',
      content: {
        total_duration_seconds: 142.8,
        word_count: 312,
        average_wpm: 131,
        segments: [
          { id: 1, start: 0.0,   end: 18.4,  text: 'In the spring of twenty twenty six, something unprecedented happened...' },
          { id: 2, start: 18.4,  end: 34.1,  text: 'The data tells a stark story. Global trust in governments has fallen...' },
          { id: 3, start: 34.1,  end: 58.9,  text: 'But this collapse did not happen in a vacuum...' },
          { id: 4, start: 58.9,  end: 82.3,  text: 'The footage from Brussels, São Paulo, Jakarta, and Detroit...' },
          { id: 5, start: 82.3,  end: 118.7, text: 'And yet — this is not a story of despair...' },
          { id: 6, start: 118.7, end: 142.8, text: 'The question now is whether these experiments can scale...' },
        ],
      },
    },

    '16': {
      kind: 'json',
      content: {
        version: '1.0',
        total_duration: 142.8,
        clips: [
          { clip_id: 1, asset: 'scene_1/asset_1/animated.mp4', narration_start: 0.0,   narration_end: 18.4,  ken_burns: 'zoom_in',   duration: 12.0 },
          { clip_id: 2, asset: 'scene_1/asset_2/image.jpg',    narration_start: 12.0,  narration_end: 18.4,  ken_burns: 'pan_left',  duration: 6.0  },
          { clip_id: 3, asset: 'scene_2/asset_1/animated.mp4', narration_start: 18.4,  narration_end: 34.1,  ken_burns: 'zoom_out',  duration: 8.0  },
          { clip_id: 4, asset: 'scene_3/asset_1/animated.mp4', narration_start: 34.1,  narration_end: 58.9,  ken_burns: 'pan_right', duration: 10.0 },
          { clip_id: 5, asset: 'scene_5/asset_1/animated.mp4', narration_start: 82.3,  narration_end: 142.8, ken_burns: 'zoom_out',  duration: 11.0 },
        ],
      },
    },

    '17': { kind: 'video', url: null },

    '18': {
      kind: 'json',
      content: {
        youtube_title: 'The Collapse of Trust: How Democracy Is Fracturing in 2026',
        youtube_description: 'In 2026, global trust in governments has hit an all-time low of 28%. This documentary explores why — and what new forms of civic life are emerging from the wreckage. From the protest squares of Brussels to the citizens\' assemblies of Dublin, this is the story of democracy under pressure.\n\n#Politics #Democracy #2026 #Documentary #Trust #CivicLife',
        hashtags: ['#Politics', '#Democracy', '#Documentary', '#2026', '#CivicLife', '#Government'],
        tags: ['political documentary', 'democracy crisis', '2026 politics', 'trust in government', 'citizens assembly', 'populism', 'civic engagement'],
      },
    },
  },

  [SCIENCE]: {
    '1': { kind: 'markdown', content: `# Research Dossier — The Quantum Revolution (2026)

## Executive Summary

Quantum computing has crossed the threshold from laboratory curiosity to practical utility. In 2026, three developments mark the inflection point:

1. **Error-corrected qubits at scale** — IBM's Condor II processor achieved 1,000 logical qubits in February 2026, enabling the first commercially useful quantum advantage.
2. **Quantum cryptography goes mainstream** — China and the EU mandated post-quantum encryption for all government communications by 2027.
3. **Drug discovery acceleration** — Two new cancer treatments discovered via quantum molecular simulation entered Phase III trials this year.

## Key Statistics

| Metric | Value |
|--------|-------|
| Market size (2026) | $12.4B |
| YoY growth | 74% |
| Active quantum startups | 847 |
| Governments with national quantum strategies | 43 |` },

    '2': { kind: 'markdown', content: `# Story Script — The Quantum Leap

## Act I: The Lab That Changed Everything

For most of human history, the atom was the smallest thing we could manipulate with precision. Then came quantum mechanics — a theory so strange that even its creators couldn't fully believe it.

Seventy years after Feynman imagined the quantum computer, it is real. And it is beginning to change everything.

## Act II: The Race

The competition for quantum supremacy is as fierce as the space race. China has invested $15 billion. The US has mobilised its national laboratories. The EU has launched its Quantum Flagship programme. Even mid-sized nations like Canada and Australia have staked claims.

But this is not just a geopolitical contest. It is a race against the clock. Our current encryption — the locks protecting every bank, every government system, every private communication — can be broken by a sufficiently powerful quantum computer.

## Act III: Promise and Peril

The promise is extraordinary: drugs designed atom by atom, materials engineered at the quantum level, climate models of unprecedented precision. The peril is equally real: a cryptographic crisis that could undermine the security infrastructure of the entire digital world.

The quantum era has arrived. How we navigate it will define the century.` },

    '3': { kind: 'markdown', content: `# Scene Plan — The Quantum Leap

---
SCENE 1 / ASSET 1
KEN_BURNS: zoom_in
VISUAL_GOAL: IBM quantum processor — close-up of golden cryogenic suspension
DURATION: 10 seconds

---
SCENE 2 / ASSET 1
KEN_BURNS: zoom_out
VISUAL_GOAL: Abstract visualisation of qubit entanglement
DURATION: 8 seconds

---
SCENE 3 / ASSET 1
KEN_BURNS: pan_left
VISUAL_GOAL: World map showing quantum investment by nation
DURATION: 9 seconds

---
SCENE 4 / ASSET 1
KEN_BURNS: zoom_in
VISUAL_GOAL: Molecular simulation — cancer drug discovery
DURATION: 11 seconds

---
SCENE 5 / ASSET 1
KEN_BURNS: zoom_out
VISUAL_GOAL: Data centre with quantum-classical hybrid racks
DURATION: 8 seconds` },

    '4': { kind: 'markdown', content: `# Asset Manifest — Quantum Revolution

---
SCENE 1 / ASSET 1
TYPE: real_image
KEN_BURNS: zoom_in
VISUAL_GOAL: Quantum processor cryogenic cooling unit
DURATION: 10 seconds

---
SCENE 2 / ASSET 1
TYPE: ai_image
KEN_BURNS: zoom_out
VISUAL_GOAL: Abstract 3D visualisation of quantum entanglement
DURATION: 8 seconds

---
SCENE 3 / ASSET 1
TYPE: ai_image
KEN_BURNS: pan_left
VISUAL_GOAL: Infographic world map with quantum investment data
DURATION: 9 seconds

---
SCENE 4 / ASSET 1
TYPE: ai_image
KEN_BURNS: zoom_in
VISUAL_GOAL: Molecular simulation rendered in 3D
DURATION: 11 seconds

---
SCENE 5 / ASSET 1
TYPE: real_image
KEN_BURNS: zoom_out
VISUAL_GOAL: Modern quantum data centre interior
DURATION: 8 seconds` },

    '5': { kind: 'markdown', content: `# Asset Acquisition — Quantum Revolution

SCENE 1
ASSET 1
TYPE: real_image
SEARCH_QUERY: IBM quantum processor cryogenic dilution refrigerator

SCENE 2
ASSET 1
TYPE: ai_image
AI_PROMPT: Abstract 3D visualisation of quantum entanglement, glowing spheres connected by ethereal blue threads, dark space background, photorealistic, cinematic lighting, 4K

SCENE 3
ASSET 1
TYPE: ai_image
AI_PROMPT: Clean infographic world map showing quantum computing investment by nation, glowing data points, dark background, blue and gold colour scheme, 4K

SCENE 4
ASSET 1
TYPE: ai_image
AI_PROMPT: 3D molecular structure simulation of a complex drug molecule, atoms rendered as glowing spheres with bonds between them, scientific visualisation, dark background, photorealistic

SCENE 5
ASSET 1
TYPE: real_image
SEARCH_QUERY: quantum computing data centre server racks hardware` },

    '6': {
      kind: 'asset_list',
      files: [
        { path: 'assets/scene_1/asset_1/search_query.txt', name: 'search_query.txt', folder: 'scene_1/asset_1' },
        { path: 'assets/scene_2/asset_1/generated.txt', name: 'generated.txt', folder: 'scene_2/asset_1' },
        { path: 'assets/scene_3/asset_1/generated.txt', name: 'generated.txt', folder: 'scene_3/asset_1' },
        { path: 'assets/scene_4/asset_1/generated.txt', name: 'generated.txt', folder: 'scene_4/asset_1' },
        { path: 'assets/scene_5/asset_1/search_query.txt', name: 'search_query.txt', folder: 'scene_5/asset_1' },
      ],
    },

    '7': {
      kind: 'image_list',
      images: [
        { path: 'assets/scene_1/asset_1/image.jpg', url: 'https://picsum.photos/seed/quantum1/640/360', label: 'scene_1/asset_1' },
        { path: 'assets/scene_2/asset_1/image.png', url: 'https://picsum.photos/seed/qubit2/640/360', label: 'scene_2/asset_1' },
        { path: 'assets/scene_3/asset_1/image.png', url: 'https://picsum.photos/seed/map3/640/360', label: 'scene_3/asset_1' },
        { path: 'assets/scene_4/asset_1/image.png', url: 'https://picsum.photos/seed/molecule4/640/360', label: 'scene_4/asset_1' },
        { path: 'assets/scene_5/asset_1/image.jpg', url: 'https://picsum.photos/seed/datacenter5/640/360', label: 'scene_5/asset_1' },
      ],
    },

    '8': {
      kind: 'animation_list',
      items: [
        { path: 'assets/scene_1/asset_1/animated.txt', label: 'scene_1/asset_1', text: 'The camera begins at distance, then slowly pushes into the golden lattice of the quantum processor\'s cryogenic chamber. The intricate superconducting loops come into sharp focus. The image has the quality of a cathedral — something built with tremendous precision for a purpose that transcends ordinary understanding.' },
        { path: 'assets/scene_2/asset_1/animated.txt', label: 'scene_2/asset_1', text: 'The quantum entanglement visualisation slowly expands outward — glowing nodes multiply and connect across the frame. The camera pulls back to reveal an ever-growing network. The motion has an organic quality, like watching neurons form in slow motion. Light pulses travel the connections in both directions simultaneously.' },
        { path: 'assets/scene_3/asset_1/animated.txt', label: 'scene_3/asset_1', text: 'The world map pans gently from west to east. Investment circles pulse and grow on each nation as the camera traverses continents. The data points have a heartbeat quality — each pulse representing billions of dollars and thousands of scientists. The race is visible, quantified, alive.' },
        { path: 'assets/scene_4/asset_1/animated.txt', label: 'scene_4/asset_1', text: 'The molecular structure rotates slowly in space while the camera zooms toward a specific bond. The quantum simulation arrows show electron probability clouds shifting and settling. There is beauty in the mathematics of matter at this scale.' },
        { path: 'assets/scene_5/asset_1/animated.txt', label: 'scene_5/asset_1', text: 'The camera starts close to the quantum hardware racks, then pulls back to reveal the scale of the entire data centre. Rows of cryogenic units stretch into the distance. The facility hums with the quiet confidence of infrastructure that will define an era.' },
      ],
    },

    '9': {
      kind: 'video_list',
      videos: [
        { scene_id: '1', asset_id: '1', label: 'scene_1/asset_1', thumbnail_url: 'https://picsum.photos/seed/quantum1/640/360', video_url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4', status: 'done' },
        { scene_id: '2', asset_id: '1', label: 'scene_2/asset_1', thumbnail_url: 'https://picsum.photos/seed/qubit2/640/360', video_url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4', status: 'done' },
        { scene_id: '3', asset_id: '1', label: 'scene_3/asset_1', thumbnail_url: 'https://picsum.photos/seed/map3/640/360', video_url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4', status: 'done' },
        { scene_id: '4', asset_id: '1', label: 'scene_4/asset_1', thumbnail_url: 'https://picsum.photos/seed/molecule4/640/360', video_url: null, status: 'pending' },
        { scene_id: '5', asset_id: '1', label: 'scene_5/asset_1', thumbnail_url: 'https://picsum.photos/seed/datacenter5/640/360', video_url: null, status: 'pending' },
      ],
    },

    '10': { kind: 'markdown', content: `# Narration Script — The Quantum Leap

=== ELEVENLABS VERSION ===

For most of human history, the atom was the smallest thing we could manipulate with precision. Then came quantum mechanics — a theory so strange that even its creators couldn't quite believe it.

Seventy years after Richard Feynman first imagined the quantum computer, it is real. And it is beginning to change everything.

In twenty twenty six, a quantum processor achieved what classical computers cannot — simulating the behaviour of complex molecules with perfect fidelity. The result: two new cancer treatments, discovered in months, that would have taken decades using conventional methods.

The race for quantum supremacy is as fierce as any geopolitical contest in modern history. China has invested fifteen billion dollars. The United States has mobilised its national laboratories. Forty-three countries now have national quantum strategies.

But with extraordinary power comes extraordinary risk. The encryption protecting every bank, every government system, every private message — it can be broken by a sufficiently powerful quantum computer. The clock is ticking on the security infrastructure of the entire digital world.

The quantum era has arrived. The only question now is whether we are wise enough to navigate it.` },

    '11': { kind: 'audio', url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3' },

    '12': { kind: 'text', content: `Music prompt for "The Quantum Leap" — Science documentary 2026.

Aesthetic: Intellectual wonder meets existential stakes. Think Jóhann Jóhannsson's "The Theory of Everything" crossed with Brian Eno's ambient soundscapes.

Structure:
- Opening: Sparse, crystalline piano notes. Space between each note. The sense of peering into something vast and incomprehensible.
- Build: Slow string introduction. A sense of momentum and discovery. Not triumphant yet — more like cautious optimism.
- Peak: Full orchestral swell. The moment of breakthrough. Strings, brass, and subtle choral elements.
- Resolution: Returns to sparse piano. The weight of what has been discovered settles. Wonder tinged with responsibility.

Key themes: Curiosity, discovery, the sublime, the uncanny.
BPM: 52–65. Unhurried. Scientific.` },

    '13': { kind: 'audio', url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3' },

    '14': { kind: 'text', content: `ASSET INVENTORY — science/2026-08-19_091544
Generated: 2026-08-19 13:22:07
==================================================

SCENE 1 / ASSET 1
  Type      : real_image
  File      : assets/scene_1/asset_1/image.jpg
  Size      : 1.1 MB
  Source    : Wikimedia Commons
  Status    : READY

SCENE 2 / ASSET 1
  Type      : ai_image
  File      : assets/scene_2/asset_1/image.png
  Size      : 2.3 MB
  Status    : READY

SCENE 3 / ASSET 1
  Type      : ai_image
  File      : assets/scene_3/asset_1/image.png
  Size      : 1.7 MB
  Status    : READY

SCENE 4 / ASSET 1
  Type      : ai_image
  File      : assets/scene_4/asset_1/image.png
  Size      : 1.9 MB
  Status    : READY

SCENE 5 / ASSET 1
  Type      : real_image
  File      : assets/scene_5/asset_1/image.jpg
  Size      : 943 KB
  Source    : Pexels
  Status    : READY

SUMMARY
  Total assets : 5
  Ready        : 5
  Missing      : 0
  Animated     : 5` },

    '15': {
      kind: 'json',
      content: {
        total_duration_seconds: 138.2,
        word_count: 298,
        average_wpm: 129,
        segments: [
          { id: 1, start: 0.0,  end: 21.4, text: 'For most of human history, the atom was the smallest thing...' },
          { id: 2, start: 21.4, end: 42.8, text: 'In twenty twenty six, a quantum processor achieved...' },
          { id: 3, start: 42.8, end: 71.2, text: 'The race for quantum supremacy is as fierce...' },
          { id: 4, start: 71.2, end: 104.6, text: 'But with extraordinary power comes extraordinary risk...' },
          { id: 5, start: 104.6, end: 138.2, text: 'The quantum era has arrived...' },
        ],
      },
    },

    '16': {
      kind: 'json',
      content: {
        version: '1.0',
        total_duration: 138.2,
        clips: [
          { clip_id: 1, asset: 'scene_1/asset_1/animated.mp4', narration_start: 0.0,  narration_end: 21.4, ken_burns: 'zoom_in',  duration: 10.0 },
          { clip_id: 2, asset: 'scene_2/asset_1/animated.mp4', narration_start: 21.4, narration_end: 42.8, ken_burns: 'zoom_out', duration: 8.0  },
          { clip_id: 3, asset: 'scene_3/asset_1/animated.mp4', narration_start: 42.8, narration_end: 71.2, ken_burns: 'pan_left', duration: 9.0  },
          { clip_id: 4, asset: 'scene_4/asset_1/animated.mp4', narration_start: 71.2, narration_end: 104.6, ken_burns: 'zoom_in', duration: 11.0 },
          { clip_id: 5, asset: 'scene_5/asset_1/animated.mp4', narration_start: 104.6, narration_end: 138.2, ken_burns: 'zoom_out', duration: 8.0 },
        ],
      },
    },

    '17': { kind: 'video', url: 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4' },

    '18': {
      kind: 'json',
      content: {
        youtube_title: 'The Quantum Leap: How Quantum Computing Is Changing Everything in 2026',
        youtube_description: 'In 2026, quantum computing has crossed from theory to reality. This documentary explores the breakthroughs, the geopolitical race, and the existential risks of the quantum era — from cancer-killing molecules to the threat to all digital encryption.\n\n#QuantumComputing #Science #Technology #2026 #Documentary #IBM #Physics',
        hashtags: ['#QuantumComputing', '#Science', '#Technology', '#Documentary', '#2026', '#Physics'],
        tags: ['quantum computing', 'quantum revolution', 'science documentary', 'IBM quantum', 'quantum cryptography', '2026 science', 'qubit'],
      },
    },
  },

  [TECH]: {
    '1': { kind: 'markdown', content: `# Research Dossier — The AI Regulation Reckoning (2026)

## Executive Summary

2026 marks the year that AI regulation moved from aspiration to enforcement. Three landmark developments:

1. **EU AI Act enforcement begins** — The first fines (€240M against two unnamed social media companies) were issued in Q1 2026 under the new high-risk AI provisions.
2. **US Executive Order 14845** — The White House mandated safety testing for all frontier AI models before deployment.
3. **The Global AI Safety Compact** — 67 nations signed a non-binding agreement on minimum AI safety standards.` },

    '2': { kind: 'markdown', content: `# Story Script — The Reckoning

## Act I: The Wild West Era Ends

For five years, the most powerful AI systems ever built were deployed with minimal oversight. The consequences were real and measurable — and they became impossible to ignore.

## Act II: The Regulatory Wave

The EU moved first. Then the US. Then a cascade of national legislatures discovered that their citizens expected them to have opinions about systems that could write laws, diagnose cancer, and influence elections.

## Act III: Uncertain Ground

No one knows if the regulation will work. The technology moves faster than any legislature. And the companies building it have more resources than most governments.

The reckoning has arrived. The verdict is still out.` },

    '3': { kind: 'markdown', content: `# Scene Plan — The Reckoning

---
SCENE 1 / ASSET 1
KEN_BURNS: zoom_in
VISUAL_GOAL: EU Parliament in session, AI regulation debate
DURATION: 10 seconds

---
SCENE 2 / ASSET 1
KEN_BURNS: pan_right
VISUAL_GOAL: AI model training server farm
DURATION: 8 seconds` },

    '4': { kind: 'markdown', content: `# Asset Manifest — AI Regulation

---
SCENE 1 / ASSET 1
TYPE: real_image
KEN_BURNS: zoom_in
VISUAL_GOAL: EU Parliament chamber
DURATION: 10 seconds

---
SCENE 2 / ASSET 1
TYPE: real_image
KEN_BURNS: pan_right
VISUAL_GOAL: Large GPU server farm
DURATION: 8 seconds` },

    '5': { kind: 'markdown', content: `# Asset Acquisition — AI Regulation

SCENE 1
ASSET 1
TYPE: real_image
SEARCH_QUERY: European Parliament chamber AI regulation debate session

SCENE 2
ASSET 1
TYPE: real_image
SEARCH_QUERY: GPU server farm data centre AI training` },
  },
}

// ─────────────────────────────────────────────────────────────────────────────
// Content lookup helper
// ─────────────────────────────────────────────────────────────────────────────

function getContent(domain: string, stepId: string, run: RunState): object | null {
  const { completed } = resolveRun(run)
  const stepNum = parseInt(stepId)

  // Only return content if the step is done or currently running
  if (stepNum > completed && !run.failed_steps.includes(stepId)) return null

  // Domain-specific content
  const domainContent = CONTENT[domain]?.[stepId]
  if (domainContent) return domainContent

  // Generic fallbacks
  return null
}

// ─────────────────────────────────────────────────────────────────────────────
// Handlers
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Inference handlers — mock the AI inference server (/api/*)
// Always active when VITE_MOCK=true
// ─────────────────────────────────────────────────────────────────────────────

export const inferenceHandlers = [
  http.post('/api/generate', async () => {
    await delay(400)
    const jobId = `mock-${Math.random().toString(36).slice(2, 10)}`
    inferencePollCounts[jobId] = 0
    return HttpResponse.json({ job_id: jobId, num_frames: 81, fps: 16, duration_seconds: 5.06, width: 1280, height: 720, seed: null })
  }),

  http.get('/api/status/:jobId', async ({ params }) => {
    await delay(300)
    const jobId = params.jobId as string
    const count = (inferencePollCounts[jobId] ?? 0) + 1
    inferencePollCounts[jobId] = count
    let status: 'pending' | 'processing' | 'done' = 'pending'
    if (count === 2) status = 'processing'
    if (count >= 3) status = 'done'
    return HttpResponse.json({ job_id: jobId, status, error: null })
  }),

  http.get('/api/download/:jobId', async () => {
    await delay(200)
    return new HttpResponse(null, { status: 200 })
  }),
]

// ─────────────────────────────────────────────────────────────────────────────
// Tasks handlers — mock the pipeline tasks server (/tasks/*)
// Only active when VITE_MOCK_TASKS=true. Set VITE_MOCK_TASKS=false to use the
// real backend/tasks.py server, which reads directly from workspace/ on disk.
// ─────────────────────────────────────────────────────────────────────────────

export const tasksHandlers = [
  // ─── Tasks: list all runs ─────────────────────────────────────────────────

  http.get('/tasks/runs', async ({ request }) => {
    await delay(180)
    const domainFilter = new URL(request.url).searchParams.get('domain')
    const all = Object.values(runStore)
    const filtered = domainFilter ? all.filter(r => r.domain === domainFilter) : all
    return HttpResponse.json(filtered.map(toSummary))
  }),

  // ─── Tasks: start new run ─────────────────────────────────────────────────

  http.post('/tasks/runs', async ({ request }) => {
    await delay(300)
    const body = await request.json() as { domain: string; fresh: boolean; preview_only?: boolean }
    const ts = new Date().toISOString().slice(0, 19).replace('T', '_').replace(/:/g, '')
    const runId = ts.slice(0, 15)
    const key = `${body.domain}/${runId}`
    const isPreview = !!(body.fresh && body.preview_only)
    const newRun: RunState = {
      domain: body.domain,
      run_id: runId,
      workspace: `workspace/${body.domain}/${runId}`,
      created_at: new Date().toISOString(),
      // Full pipeline auto-run is disabled by default (ENABLE_FULL_PIPELINE=false):
      // only the step-1 preview flow auto-progresses. Full runs start inactive —
      // steps must be run individually.
      active: isPreview,
      active_step: isPreview ? '1' : null,
      start_step: 0,
      start_time: Date.now(),
      ms_per_step: isPreview ? 3000 : 8000, // preview: step 1 completes in 3s
      max_step: isPreview ? 1 : 0,
      steps_completed: 0,
      steps_failed: 0,
      steps_total: 18,
      videos: [],
      failed_steps: [],
    }
    runStore[key] = newRun
    return HttpResponse.json({
      run_id: runId,
      domain: body.domain,
      workspace: newRun.workspace,
      fresh: body.fresh,
      preview_only: isPreview,
      message: isPreview ? 'Preview started — awaiting approval after step 1' : 'Workspace ready — run steps individually',
    })
  }),

  // ─── Tasks: continue after preview approval ───────────────────────────────

  http.post('/tasks/runs/:domain/:runId/continue', async () => {
    await delay(200)
    // Gated behind ENABLE_FULL_PIPELINE, which is disabled by default — mirrors
    // the real backend's 409 response.
    return HttpResponse.json({ detail: 'Full pipeline run is disabled' }, { status: 409 })
  }),

  // ─── Tasks: run status ────────────────────────────────────────────────────

  http.get('/tasks/runs/:domain/:runId', async ({ params }) => {
    await delay(120)
    const key = `${params.domain}/${params.runId}`
    const run = runStore[key]
    if (!run) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })

    const { activeStep, active } = resolveRun(run)

    // Build step list, applying rerun overrides
    const steps = buildStepList(run).map(step => {
      const rerunStatus = getRerunStatus(run.domain, run.run_id, step.id)
      if (rerunStatus) return { ...step, status: rerunStatus }
      return step
    })

    return HttpResponse.json({
      run_id: run.run_id,
      domain: run.domain,
      voice_id: null,
      workspace: run.workspace,
      active: active || reruns.some(e => e.domain === run.domain && e.runId === run.run_id && Date.now() - e.startedAt < RERUN_DURATION_MS),
      active_step: activeStep,
      steps,
    })
  }),

  // ─── Tasks: run/rerun a step ──────────────────────────────────────────────

  http.post('/tasks/runs/:domain/:runId/steps/:stepId', async ({ params }) => {
    await delay(180)
    reruns.push({ domain: params.domain as string, runId: params.runId as string, stepId: params.stepId as string, startedAt: Date.now() })
    return HttpResponse.json({ message: 'Step queued', step_id: params.stepId, force: true })
  }),

  // ─── Tasks: step content ──────────────────────────────────────────────────

  http.get('/tasks/runs/:domain/:runId/steps/:stepId/content', async ({ params }) => {
    await delay(250)
    const domain = params.domain as string
    const runId  = params.runId  as string
    const stepId = params.stepId as string
    const key  = `${domain}/${runId}`
    const run  = runStore[key]

    if (!run) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })

    // Check rerun state — show "running" placeholder if step is currently rerunning
    const rerunStatus = getRerunStatus(domain, runId, stepId)
    if (rerunStatus === 'running') {
      return HttpResponse.json({ kind: 'markdown', content: null })
    }

    const content = getContent(domain, stepId, run)
    if (content) return HttpResponse.json(content)

    // Step is pending (not yet run)
    return HttpResponse.json({ kind: 'markdown', content: null })
  }),

  // ─── Tasks: update step content ──────────────────────────────────────────

  http.put('/tasks/runs/:domain/:runId/steps/:stepId/content', async () => {
    await delay(300)
    return HttpResponse.json({ message: 'Content updated' })
  }),

  // ─── Settings ────────────────────────────────────────────────────────────

  http.get('/tasks/settings', async () => {
    await delay(150)
    return HttpResponse.json({
      fields: [
        { key: 'GEMINI_API_KEY',     label: 'Gemini API Key',     secret: true },
        { key: 'ELEVENLABS_API_KEY', label: 'ElevenLabs API Key', secret: true },
        { key: 'PEXELS_API_KEY',     label: 'Pexels API Key',     secret: true },
        { key: 'PIXABAY_API_KEY',    label: 'Pixabay API Key',    secret: true },
        { key: 'RUNPOD_URL',         label: 'RunPod URL',         secret: false },
      ],
      values: {
        GEMINI_API_KEY: '',
        ELEVENLABS_API_KEY: '',
        PEXELS_API_KEY: '',
        PIXABAY_API_KEY: '',
        RUNPOD_URL: '',
      },
    })
  }),

  http.put('/tasks/settings', async () => {
    await delay(250)
    return HttpResponse.json({ message: 'Settings saved' })
  }),

  // ─── Tasks: save asset text files ────────────────────────────────────────

  http.put('/tasks/runs/:domain/:runId/assets/:sceneId/:assetId', async () => {
    await delay(250)
    return HttpResponse.json({ message: 'Asset files saved' })
  }),

  // ─── Tasks: upload asset image ────────────────────────────────────────────

  http.post('/tasks/runs/:domain/:runId/assets/:sceneId/:assetId/image', async () => {
    await delay(400)
    return HttpResponse.json({ message: 'Image uploaded', url: 'https://picsum.photos/seed/upload/640/360' })
  }),

  // ─── Tasks: delete run (cancel preview) ──────────────────────────────────

  http.delete('/tasks/runs/:domain/:runId', async ({ params }) => {
    await delay(150)
    const key = `${params.domain}/${params.runId}`
    delete runStore[key]
    return HttpResponse.json({ message: 'Run deleted' })
  }),
]

// Combined export for backward compatibility
export const handlers = [...inferenceHandlers, ...tasksHandlers]
