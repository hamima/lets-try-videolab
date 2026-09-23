# VidLife Frontend

React + Vite + TypeScript frontend for the Wan I2V video generation server.

## Stack

| Tool | Purpose |
|---|---|
| Vite + React + TypeScript | Scaffolding and dev server |
| Tailwind CSS v4 | Styling |
| shadcn/ui | UI components (Button, Card, Badge, Input, etc.) |
| React Router v6 | Client-side routing |
| Axios | HTTP client (typed API wrapper in `src/api/client.ts`) |
| MSW (Mock Service Worker) | Mock backend responses for local development |

---

## Prerequisites

- Node 18+
- npm 9+

---

## Install

```bash
cd frontend
npm install
```

---

## Run locally (with mocks — no AI backend needed)

Mocks are enabled by default via `.env.local`:

```bash
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

MSW intercepts all `/api/*` requests and returns realistic fake responses:
- `POST /api/generate` → returns a fake `job_id` after ~400ms
- `GET /api/status/:jobId` → cycles through `pending → processing → done` over 3 polls
- `GET /api/download/:jobId` → returns 200 (no real file)

To **disable** mocks and hit the real backend, comment out or delete `.env.local`, or set:

```bash
VITE_MOCK=false npm run dev
```

---

## Run against real backend

1. Start the backend on port 8080:
   ```bash
   cd backend
   bash setup.sh --start-only
   ```
2. Start the frontend without mock:
   ```bash
   VITE_MOCK=false npm run dev
   ```

The Vite dev server proxies all `/api/*` requests to `http://localhost:8080`, so no CORS configuration is needed.

---

## Build for production

```bash
npm run build
```

Output goes to `dist/`. Serve with any static file server. In production, configure your web server (nginx, Caddy, etc.) to proxy `/api/*` to the backend.

---

## Project structure

```
src/
├── api/
│   └── client.ts          # Typed Axios wrapper (generate, getStatus, getDownloadUrl)
├── components/
│   └── ui/                # shadcn/ui components (Button, Card, Badge, Input, etc.)
├── lib/
│   └── utils.ts           # cn() helper (clsx + tailwind-merge)
├── mocks/
│   ├── handlers.ts        # MSW request handlers — edit these to change mock behaviour
│   └── browser.ts         # MSW browser worker setup
├── pages/
│   ├── GeneratePage.tsx   # / — upload form
│   └── StatusPage.tsx     # /status/:jobId — polling + download
├── App.tsx                # Router
├── main.tsx               # Entry point (starts MSW if VITE_MOCK=true)
└── index.css              # Tailwind + shadcn CSS variables
```

---

## Adding shadcn/ui components

```bash
npx shadcn@latest add <component>
```

Example:
```bash
npx shadcn@latest add dialog
npx shadcn@latest add select
```

Components are copied into `src/components/ui/` and owned by you.

---

## Customising mocks

Edit `src/mocks/handlers.ts` to adjust mock behaviour — response shapes, delays, error scenarios:

```ts
// Simulate a failed job
http.get('/api/status/:jobId', () => {
  return HttpResponse.json({ job_id: '...', status: 'failed', error: 'Out of memory' })
})
```

The mock state machine in `handlers.ts` tracks poll counts per job ID to simulate progression from `pending → processing → done`.
