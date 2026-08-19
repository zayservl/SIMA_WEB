import { NavLink, useParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useProjectStore } from '@/store/projectStore'
import { LayoutDashboard, Upload, Mountain, TreePine, Droplets, ListChecks, Database, Settings, SlidersHorizontal } from 'lucide-react'
import type { JobType } from '@/api/types'
import { checkDependencies } from '@/lib/dependencies'

// Состояние этапа конвейера для индикатора в меню. Порядок работы должен
// читаться из меню, а не выясняться методом проб: помимо «идёт/готово» нужно
// видеть, что модуль ждёт чужого результата.
type StageState = 'idle' | 'blocked' | 'running' | 'partial' | 'success' | 'failed'

interface Stage {
  state: StageState
  title: string
}

const stageDot: Record<StageState, string> = {
  idle: 'bg-slate-300',
  blocked: 'bg-slate-300 ring-1 ring-amber-300',
  running: 'bg-amber-400 animate-pulse',
  partial: 'bg-amber-400',
  success: 'bg-emerald-500',
  failed: 'bg-red-500',
}

const IDLE: Stage = { state: 'idle', title: 'не запускался' }

function moduleStage(projectId: string, type: JobType, jobs: ReturnType<typeof useProjectStore.getState>['jobs']): Stage {
  const typed = jobs.filter((j) => j.project_id === projectId && j.type === type)
  const latest = typed.length
    ? typed.reduce((a, b) => (a.started_at && b.started_at && a.started_at > b.started_at ? a : b))
    : undefined

  if (latest?.status === 'running' || latest?.status === 'queued') {
    return { state: 'running', title: 'идёт расчёт' }
  }
  if (latest?.status === 'success') {
    return latest.tiles_failed > 0
      ? { state: 'partial', title: `готово ${latest.tiles_done} из ${latest.tiles_total} тайлов` }
      : { state: 'success', title: 'рассчитан' }
  }
  if (latest?.status === 'failed') return { state: 'failed', title: 'расчёт завершился ошибкой' }

  // Ни одной сессии: показываем, чего модуль ждёт, чтобы стать доступным.
  const deps = checkDependencies(projectId, type)
  if (!deps.ok) {
    return { state: 'blocked', title: 'ждёт: ' + deps.missing.map((m) => `${m.layer} (${m.tab})`).join(', ') }
  }
  return IDLE
}

function useStages(projectId?: string): { upload: Stage } & Record<JobType, Stage> {
  // Подписка на обе ветки стора: индикаторы зависят и от задач, и от загрузки.
  const jobs = useProjectStore((s) => s.jobs)
  const inputTiles = useProjectStore((s) => (projectId ? s.inputTiles[projectId] : undefined))

  if (!projectId) {
    return { upload: IDLE, relief: IDLE, forest: IDLE, water: IDLE }
  }
  return {
    upload: inputTiles?.length
      ? { state: 'success', title: `материалы оценены: ${inputTiles.length} тайлов` }
      : { state: 'blocked', title: 'материалы не загружены' },
    relief: moduleStage(projectId, 'relief', jobs),
    forest: moduleStage(projectId, 'forest', jobs),
    water: moduleStage(projectId, 'water', jobs),
  }
}

export function Sidebar() {
  const { projectId } = useParams()
  const stages = useStages(projectId)

  const projectNav = [
    { to: 'upload', icon: Upload, label: 'Загрузка данных', stage: stages.upload as Stage | undefined },
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
                    {item.stage && item.stage.state !== 'idle' && (
                      <span
                        title={item.stage.title}
                        className={cn('h-1.5 w-1.5 shrink-0 rounded-full', stageDot[item.stage.state])}
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