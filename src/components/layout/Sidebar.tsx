import { NavLink, useParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useProjectStore } from '@/store/projectStore'
import { LayoutDashboard, Upload, Mountain, TreePine, Droplets, ListChecks, Database, Settings, SlidersHorizontal } from 'lucide-react'
import type { JobType, JobStatus } from '@/api/types'

// Статус этапа конвейера для индикатора в сайдбаре.
type StageState = 'idle' | 'running' | 'success' | 'failed'

const stageDot: Record<StageState, string> = {
  idle: 'bg-slate-300',
  running: 'bg-amber-400 animate-pulse',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
}

const stageTitle: Record<StageState, string> = {
  idle: 'не запускался',
  running: 'в обработке',
  success: 'готово',
  failed: 'ошибка',
}

function useStageStates(projectId?: string): Record<Exclude<JobType, never>, StageState> {
  const jobs = useProjectStore((s) => s.jobs)
  if (!projectId) return { relief: 'idle', forest: 'idle', water: 'idle' } as Record<JobType, StageState>
  const out: Record<JobType, StageState> = { relief: 'idle', forest: 'idle', water: 'idle' }
  ;(['relief', 'forest', 'water'] as JobType[]).forEach((type) => {
    const typed = jobs.filter((j) => j.project_id === projectId && j.type === type)
    if (typed.length === 0) { out[type] = 'idle'; return }
    // последний по времени старт
    const latest = typed.reduce((a, b) => (a.started_at && b.started_at && a.started_at > b.started_at ? a : b))
    const map: Record<JobStatus, StageState> = {
      queued: 'idle', running: 'running', success: 'success', failed: 'failed', cancelled: 'idle',
    }
    out[type] = map[latest.status]
  })
  return out
}

export function Sidebar() {
  const { projectId } = useParams()
  const stages = useStageStates(projectId)

  const projectNav = [
    { to: 'upload', icon: Upload, label: 'Загрузка данных', stage: undefined as StageState | undefined },
    { to: 'relief', icon: Mountain, label: 'Рельеф', stage: stages.relief },
    { to: 'forest', icon: TreePine, label: 'Древостой', stage: stages.forest },
    { to: 'water', icon: Droplets, label: 'Вода', stage: stages.water },
    { to: 'tasks', icon: ListChecks, label: 'Задачи', stage: undefined },
    { to: 'data', icon: Database, label: 'Данные', stage: undefined },
    { to: 'settings', icon: SlidersHorizontal, label: 'Параметры проекта', stage: undefined },
  ]

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">С</div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">СИМА</span>
          <span className="text-[10px] text-slate-400">веб-прототип</span>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {/* Раздел: Проекты */}
        <div className="mb-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                isActive ? 'bg-brand-50 text-brand-700 font-medium' : 'text-slate-600 hover:bg-slate-50',
              )
            }
          >
            <LayoutDashboard className="h-4 w-4" />
            Проекты
          </NavLink>
        </div>

        {/* Раздел: Текущий проект (дерево) */}
        {projectId && (
          <div className="mt-3">
            <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Текущий проект
            </div>
            <div className="ml-2 border-l border-slate-200 pl-2">
              {projectNav.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.to}
                    to={`/projects/${projectId}/${item.to}`}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                        isActive ? 'bg-brand-50 text-brand-700 font-medium' : 'text-slate-600 hover:bg-slate-50',
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    {item.stage && item.stage !== 'idle' && (
                      <span
                        title={stageTitle[item.stage]}
                        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', stageDot[item.stage])}
                      />
                    )}
                  </NavLink>
                )
              })}
            </div>
          </div>
        )}

        {/* Раздел: Настройки (вне дерева) */}
        <div className="mt-4 border-t border-slate-100 pt-2">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                isActive ? 'bg-brand-50 text-brand-700 font-medium' : 'text-slate-600 hover:bg-slate-50',
              )
            }
          >
            <Settings className="h-4 w-4" />
            Настройки
          </NavLink>
        </div>
      </nav>

      <div className="border-t border-slate-200 p-3 text-[10px] text-slate-400">
        v0.1 · прототип · моки
      </div>
    </aside>
  )
}