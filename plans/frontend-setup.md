# Frontend Setup — React + Vite

Scaffold a `frontend/` directory at the project root containing a React + TypeScript app that communicates with the Wan I2V backend API (`backend/server.py`).

Key decisions:
- **Vite** for scaffolding and dev server
- **TypeScript** throughout
- **Tailwind CSS** + **shadcn/ui** for styling and components
- **React Router v6** for client-side routing (`/`, `/status/:jobId`)
- **Axios** for HTTP, wrapped in a typed API client
- **MSW (Mock Service Worker)** for local development without hitting the AI backend — enabled via `VITE_MOCK=true` in `.env.local`
- Vite dev proxy: `/api/*` → `http://localhost:8080` to avoid CORS in real mode

---

## Scaffold the Vite + React + TypeScript project

Run `npm create vite@latest frontend -- --template react-ts` from the project root.

### Install dependencies

After scaffolding, inside `frontend/`:
- `npm install react-router-dom axios`
- `npm install -D tailwindcss postcss autoprefixer msw`
- `npx tailwindcss init -p`
- shadcn/ui: `npx shadcn@latest init` (or manual `components.json`)

### Install shadcn/ui base components

Add: `button`, `card`, `input`, `label`, `badge`, `progress`

---

## Configure tooling

### Vite proxy + MSW plugin (`vite.config.ts`)

Forward `/api/*` to `http://localhost:8080` in dev. Conditionally load MSW.

### Tailwind config

Point content globs at `./src/**/*.{ts,tsx}`.

### shadcn/ui config (`components.json`)

Set baseColor, cssVariables, aliases matching Vite+TS project structure.

---

## Set up MSW mocks

### `src/mocks/handlers.ts`

Mock all three endpoints:
- `POST /api/generate` → returns a fake `job_id` after 300ms
- `GET /api/status/:jobId` → returns `processing` for first 2 polls, then `done`
- `GET /api/download/:jobId` → returns 200 (no real file in mock)

### `src/mocks/browser.ts`

Set up MSW browser worker. Started in `src/main.tsx` when `import.meta.env.VITE_MOCK === 'true'`.

### `.env.local`

```
VITE_MOCK=true
```

---

## Build the API client and pages

### `src/api/client.ts`

Typed Axios wrapper with functions:
- `generate(prompt, image): Promise<GenerateResponse>`
- `getStatus(jobId): Promise<StatusResponse>`
- `getDownloadUrl(jobId): string`

All calls go to `/api/*` (proxied in dev, relative in prod).

### Pages

- **`/` — GeneratePage**: prompt textarea, image file input, submit button; on success navigates to `/status/:jobId`
- **`/status/:jobId` — StatusPage**: polls `getStatus` every 3s, shows badge (pending/processing/done/failed), download button when done

---

## Write `frontend/README.md`

Cover:
- Prerequisites (Node 18+)
- Install: `npm install`
- Run with mocks: `VITE_MOCK=true npm run dev` (or via `.env.local`)
- Run against real backend: ensure `backend/setup.sh` is running on port 8080, then `npm run dev`
- Build for production: `npm run build`
- How mocks work (MSW, handlers file location)
- How to add a new shadcn/ui component: `npx shadcn@latest add <component>`
