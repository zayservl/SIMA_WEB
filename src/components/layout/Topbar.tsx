import { useProjectStore } from '@/store/projectStore'
import { useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import type { ProjectStatus } from '@/api/types'

const STATUS_LABEL: Record<ProjectStatus, string> = {
  empty: 'нет данных',
  uploaded: 'данные загружены',
  processing: 'идёт расчёт',
  done: 'рассчитан',
  error: 'ошибка',
}
const STATUS_VARIANT: Record<ProjectStatus, 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  empty: 'neutral', uploaded: 'info', processing: 'warning', done: 'success', error: 'danger',
}

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
            <Badge variant={STATUS_VARIANT[project.status]}>{STATUS_LABEL[project.status]}</Badge>
          </>
        )}
      </div>
    </header>
  )
}