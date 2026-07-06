import { useProjectStore } from '@/store/projectStore'
import { useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'

export function Topbar() {
  const { projectId } = useParams()
  const projects = useProjectStore((s) => s.projects)
  const project = projects.find((p) => p.id === projectId)

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {project && (
          <>
            <span className="text-sm font-semibold text-slate-900">{project.name}</span>
            <Badge variant="info">{project.status}</Badge>
          </>
        )}
      </div>
    </header>
  )
}