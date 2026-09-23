import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

async function prepare() {
  const mockInference = import.meta.env.VITE_MOCK === 'true'
  const mockTasks     = import.meta.env.VITE_MOCK_TASKS === 'true'

  if (mockInference || mockTasks) {
    const { inferenceHandlers, tasksHandlers } = await import('./mocks/handlers')
    const { createWorker } = await import('./mocks/browser')

    const active = [
      ...(mockInference ? inferenceHandlers : []),
      ...(mockTasks     ? tasksHandlers     : []),
    ]

    return createWorker(active).start({ onUnhandledRequest: 'bypass' })
  }
}

prepare().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>
  )
})
