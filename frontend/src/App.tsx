import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/Layout'
import GeneratePage from '@/pages/GeneratePage'
import StatusPage from '@/pages/StatusPage'
import TasksListPage from '@/pages/TasksListPage'
import RunDetailPage from '@/pages/RunDetailPage'
import SettingsPage from '@/pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<GeneratePage />} />
          <Route path="/status/:jobId" element={<StatusPage />} />
          <Route path="/tasks" element={<TasksListPage />} />
          <Route path="/tasks/:domain/:runId" element={<RunDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
