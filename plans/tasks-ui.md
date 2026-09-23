# Tasks UI — Pipeline Dashboard

React UI for the VidLife Tasks API (`backend/tasks.py`), built inside the existing `frontend/` app.
All UI/UX decisions are Claude-designed for clarity and productivity.

## Key decisions

| Concern | Decision |
|---|---|
| App structure | New routes in the existing React app alongside `/` and `/status/:jobId` |
| Proxy | `/tasks/*` → port 8081 added to `vite.config.ts` (separate from `/api/*` → 8080) |
| Navigation | Minimal top nav bar: "Generate" · "Pipeline" |
| Runs list | Cards grid with domain, timestamp, step progress, status badge, video count; auto-polls every 5s when any run is active |
| Run detail | Left: step timeline list. Right: slide-in side panel with step content + rerun button |
| Content viewers | Type-aware: markdown rendered as HTML, images as thumbnail grid, audio/video players, JSON/text as formatted code |
| New run | Modal dialog from runs list: domain picker + fresh/resume toggle |
| Active run polling | Auto-polls every 3s while run is active; animated spinner on executing step; stops when idle |
| Backend content endpoint | `GET /tasks/runs/{domain}/{run_id}/steps/{step_id}/content` added to `tasks.py` |
| Mocks | MSW handlers extended to cover all new `/tasks/*` endpoints |

---

## Add content endpoint to `backend/tasks.py`

The existing status endpoint only returns step status — not file content. A new endpoint reads the
output file from disk and returns it with the correct content type so the frontend can render it.

### Add `GET /tasks/runs/{domain}/{run_id}/steps/{step_id}/content`

Map each step ID to its output path and content type:

| Step | Output file | Content-Type |
|---|---|---|
| 1–5, 10, 12, 18 | `{output}` (`.md` or `.txt`) | `text/markdown` or `text/plain` |
| 6 | list of files in `assets/` tree | `application/json` (file tree) |
| 7 | all `image.png` / `image.jpg` in `assets/` | `application/json` (list of paths) |
| 8 | all `animated.txt` in `assets/` | `application/json` (list of {path, text}) |
| 9 | all `animated.mp4` in `assets/` | `application/json` (list of paths) |
| 11 | `narration.mp3` | served via separate `/tasks/files/` static route |
| 13 | `music.wav` | served via separate `/tasks/files/` static route |
| 14 | `asset_inventory.txt` | `text/plain` |
| 15 | `narration_timing.json` | `application/json` |
| 16 | `edl.json` | `application/json` |
| 17 | `output/final_video.mp4` | served via `/tasks/files/` static route |

#### Static file serving

Add `GET /tasks/files/{domain}/{run_id}/{file_path:path}` that streams any file from the workspace
as-is — used for images, audio, and video. The frontend constructs these URLs from the paths
returned by the content endpoint.

---

## Update `vite.config.ts` and Vite proxy

### Add `/tasks/*` proxy

```ts
'/tasks': {
  target: 'http://localhost:8081',
  changeOrigin: true,
}
```

No rewrite needed — the backend router is already mounted at `/tasks`.

---

## Add MSW mock handlers for tasks

Extend `src/mocks/handlers.ts` with realistic mock data for all Tasks API endpoints:

### Mock data

Create a small in-memory store of fake runs (2–3 domains, mixed statuses) and a mock step
progression similar to the existing inference mock (pending → processing → done over polls).

### Handlers to add

- `GET /tasks/runs` — returns 3–4 fake runs across domains
- `POST /tasks/runs` — creates a new fake run, returns run_id
- `GET /tasks/runs/:domain/:runId` — returns full step list with mock statuses
- `POST /tasks/runs/:domain/:runId/steps/:stepId` — marks step as queued
- `GET /tasks/runs/:domain/:runId/steps/:stepId/content` — returns fake content per step type

---

## Add typed API client for tasks

### Create `src/api/tasks.ts`

Typed Axios functions wrapping all Tasks API endpoints:

```ts
listRuns(domain?: string): Promise<RunSummary[]>
startRun(domain: string, fresh: boolean): Promise<StartRunResponse>
getRunStatus(domain: string, runId: string): Promise<RunStatus>
runStep(domain: string, runId: string, stepId: string, force: boolean): Promise<void>
getStepContent(domain: string, runId: string, stepId: string): Promise<StepContent>
fileUrl(domain: string, runId: string, filePath: string): string
```

Define TypeScript interfaces for `RunSummary`, `RunStatus`, `StepDetail`, `StepContent`.

---

## Build shared layout with top navigation

### Create `src/components/Layout.tsx`

Wraps all pages. Contains:
- Top bar: "VidLife" logo/wordmark on the left, two nav links ("Generate", "Pipeline") on the right
- Active link highlighted (underline or filled pill)
- `<Outlet />` for page content below

### Update `src/App.tsx`

Wrap existing and new routes inside `<Layout>`:

```tsx
<Route element={<Layout />}>
  <Route path="/" element={<GeneratePage />} />
  <Route path="/status/:jobId" element={<StatusPage />} />
  <Route path="/tasks" element={<TasksListPage />} />
  <Route path="/tasks/:domain/:runId" element={<RunDetailPage />} />
</Route>
```

---

## Build `TasksListPage` (`/tasks`)

### Layout

Full-width page. Header row: "Pipeline Runs" title + "New Run" button (opens modal).
Below: responsive card grid (3 columns desktop, 2 tablet, 1 mobile).

### `RunCard` component

Each card shows:
- **Domain** as a coloured tag (each domain gets a fixed hue)
- **Run ID** formatted as a readable date+time (`2026-08-20 14:30`)
- **Progress bar** — filled segments proportional to `steps_completed / steps_total`
- **Step counts** — `12 / 18 steps` · `2 failed` (if any)
- **Status badge** — `Active` (pulsing green dot) · `Done` · `Failed` · `Partial`
- **Video count** — `3 videos` with a film icon, only shown if `videos.length > 0`
- Entire card is clickable → navigates to `/tasks/{domain}/{run_id}`

### Auto-polling

If any run is `active`, set a 5-second interval to refetch `GET /tasks/runs`.
Clear the interval when all runs are idle.

### `NewRunModal` component

Dialog with:
- **Domain** — dropdown (all 8 supported domains)
- **Mode toggle** — "Resume latest" (default) / "Fresh start" (radio or segmented control)
- "Start Run" button — calls `POST /tasks/runs`, then navigates to the new run's detail page

---

## Build `RunDetailPage` (`/tasks/:domain/:runId`)

### Layout

Two-column layout:
- **Left panel** (fixed width ~320px): scrollable step timeline
- **Right panel** (flex-grow): step content viewer (empty state until a step is selected)

On mobile: full-width step list; tapping a step slides in content as a bottom sheet.

### Step timeline (left panel)

Vertical list of all 18 steps. Each row:
- Step number pill (coloured by status: grey=pending, blue=running, green=done, red=failed)
- Step name
- Step type label (small, muted)
- Animated spinner replacing the pill when status is `running`
- Clicking a row selects it and loads content in the right panel

### Step content panel (right panel)

Header: step name + status badge + "Rerun" button (calls `POST .../steps/{id}` with `force: true`)

Content area below renders based on step type:

#### `MarkdownViewer`
Renders markdown as HTML using a lightweight library (`marked` or `@uiw/react-markdown-preview`).
Used for steps 1–5, 10, 12, 18.

#### `ImageGridViewer`
For step 7 — fetches list of image paths, renders a responsive grid of `<img>` tags using
`/tasks/files/...` URLs. Click to enlarge in a lightbox.

#### `TextViewer`
Preformatted `<pre>` block with syntax highlighting for JSON (steps 15, 16), plain text otherwise
(steps 6, 8, 14).

#### `AudioPlayer`
Native `<audio controls>` with `src` pointing to `/tasks/files/...`.
Used for steps 11 (narration.mp3) and 13 (music.wav).

#### `VideoPlayer`
Native `<video controls>` styled full-width. Used for steps 9 (animated clips grid) and 17 (final video).

#### Empty states
- Step `pending`: "This step hasn't run yet." with a rerun button.
- Step `failed`: Error message from state + rerun button.
- Step `running`: Skeleton loader / spinner while content loads.

### Auto-polling

While `run.active === true`, poll `GET /tasks/runs/{domain}/{run_id}` every 3 seconds.
Update step statuses in place. Stop when `active` becomes false.
When the active step changes, auto-select it in the timeline and fetch its content.

### "Rerun" and "Fresh Start" actions

- **Rerun step**: calls `POST .../steps/{id}` with `{ force: true }`, then resumes polling
- **Fresh start**: calls `POST /tasks/runs` with `{ domain, fresh: true }`, navigates to new run ID

---

## Add new shadcn/ui components

Install via `npx shadcn@latest add`:

- `dialog` — for NewRunModal
- `select` — for domain picker in modal
- `progress` — for step progress bar on cards
- `separator` — for panel dividers
- `skeleton` — for loading states in content panel
- `scroll-area` — for the scrollable step timeline

---

## Acceptance criteria

- `/tasks` lists all runs fetched from `GET /tasks/runs`, auto-refreshes while any run is active
- Clicking a run navigates to `/tasks/{domain}/{run_id}`
- Run detail page shows all 18 steps with correct statuses
- Active step has animated spinner; statuses update every 3s automatically
- Clicking a step loads its content in the right panel
- Content renders correctly for each type (markdown, image, audio, video, JSON, text)
- "New Run" modal opens, allows domain + mode selection, starts run and navigates to it
- "Rerun" button on any step triggers a rerun and resumes polling
- All interactions work with MSW mocks (`VITE_MOCK=true`)
- Build passes with no TypeScript errors
