import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from '@/components/Layout'
import GeneratePage from '@/pages/GeneratePage'
import StatusPage from '@/pages/StatusPage'
import TasksListPage from '@/pages/TasksListPage'
import RunDetailPage from '@/pages/RunDetailPage'
import RunWizardPage from '@/pages/RunWizardPage'
import SettingsPage from '@/pages/SettingsPage'
import SignInPage from '@/pages/SignInPage'
import { AuthProvider, useAuth } from '@/lib/auth'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return null
  if (!user) {
    return <Navigate to="/signin" state={{ from: location.pathname + location.search }} replace />
  }
  return <>{children}</>
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (!user?.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route path="/" element={<GeneratePage />} />
            <Route path="/status/:jobId" element={<StatusPage />} />
            <Route path="/tasks" element={<TasksListPage />} />
            <Route path="/tasks/:domain/:runId" element={<RunDetailPage />} />
            <Route path="/tasks/:domain/:runId/wizard/:stepId" element={<RunWizardPage />} />
            <Route path="/settings" element={<RequireAdmin><SettingsPage /></RequireAdmin>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
