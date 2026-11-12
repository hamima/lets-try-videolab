import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/tasks': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        // The frontend's own SPA pages also live under /tasks (TasksListPage,
        // RunDetailPage, RunWizardPage), so a hard refresh/direct load of a
        // URL like /tasks/political/2026-10-20_144349 is a real browser
        // navigation, not an API call. Without this, that request gets
        // proxied straight to the backend, which has no matching route, and
        // the browser shows FastAPI's bare 404 JSON instead of the app.
        // Every real backend route under /tasks starts with one of these
        // sub-paths (see backend/tasks.py, settings.py, auth.py) — anything
        // else is an SPA route, so let Vite serve index.html for it instead.
        // (Deliberately not inferring this from the Accept header: the final
        // video's download link and <video> element also live under
        // /tasks/files/... and some browsers send `Accept: text/html` for
        // those requests too.)
        bypass: (req) => {
          const TASKS_API_PREFIXES = ['/tasks/runs', '/tasks/auth', '/tasks/settings', '/tasks/files', '/tasks/estimate-cost']
          const isApiRequest = TASKS_API_PREFIXES.some((p) => req.url?.startsWith(p))
          if (!isApiRequest) return '/index.html'
        },
      },
    },
  },
})
