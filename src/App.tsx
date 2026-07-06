import { Routes, Route } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import Dashboard from '@/pages/Dashboard'
import Settings from '@/pages/Settings'
import Upload from '@/pages/Upload'
import Relief from '@/pages/Relief'
import Forest from '@/pages/Forest'
import Water from '@/pages/Water'
import Tasks from '@/pages/Tasks'
import Data from '@/pages/Data'
import ProjectSettings from '@/pages/ProjectSettings'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/projects/:projectId/upload" element={<Upload />} />
        <Route path="/projects/:projectId/relief" element={<Relief />} />
        <Route path="/projects/:projectId/forest" element={<Forest />} />
        <Route path="/projects/:projectId/water" element={<Water />} />
        <Route path="/projects/:projectId/tasks" element={<Tasks />} />
        <Route path="/projects/:projectId/data" element={<Data />} />
        <Route path="/projects/:projectId/settings" element={<ProjectSettings />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}