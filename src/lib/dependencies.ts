// Проверка зависимостей модулей СИМА v2.
// Чистая функция (не использует хуки React) — обращается к store через getState().
// Используется страницами Forest/Water для блокировки запуска при отсутствии
// необходимых входных данных (assessment / предыдущих задач).

import { useProjectStore } from '@/store/projectStore'
import type { JobType, ReliefSource } from '@/api/types'

export interface DependencyCheck {
  ok: boolean
  missing: { layer: string; tab: string }[]
}

// Источник, закрывающий зависимость «Древостоя» от предыдущего расчёта: ЦММ из
// завершённой сессии «Рельефа». Производные рельефа отдельно не выбираются —
// они берутся из той же сессии. «Вода» считается только по АФС и от «Рельефа»
// не зависит.
export interface DependencySources {
  dsm_source?: ReliefSource
}

// Проверки загруженных исходных материалов. АФС и ВЛС проверяются раздельно:
// без АФС проект работает в режиме «только ВЛС» (Рельеф и Древостой без
// детекции крон), без ВЛС не считается ничего, кроме «Воды».
function hasVls(projectId: string): boolean {
  const { assessment } = useProjectStore.getState()
  return !!assessment[projectId]?.vls
}

export function hasAfs(projectId: string): boolean {
  const { assessment } = useProjectStore.getState()
  return !!assessment[projectId]?.afs
}

// Проверка, что в проекте есть успешно завершённая задача данного типа.
function hasSuccessfulJob(projectId: string, type: JobType): boolean {
  const { jobs } = useProjectStore.getState()
  return jobs.some((j) => j.project_id === projectId && j.type === type && j.status === 'success')
}

// Источник удовлетворяет зависимости, если пользователь загрузил свой .geotiff
// либо выбрал конкретную завершённую сессию расчёта в системе.
function sourceSatisfied(source: ReliefSource | undefined): boolean {
  if (!source) return false
  if (source.kind === 'upload') return !!source.upload_path
  return !!source.system_session_id
}

export function checkDependencies(projectId: string, module: JobType, sources?: DependencySources): DependencyCheck {
  const missing: { layer: string; tab: string }[] = []

  if (module === 'relief') {
    // Рельеф считается по ВЛС: без АФС модуль работает полностью.
    if (!hasVls(projectId)) {
      missing.push({ layer: 'ВЛС', tab: 'Загрузка данных' })
    }
  } else if (module === 'forest') {
    if (!hasVls(projectId)) {
      missing.push({ layer: 'ВЛС', tab: 'Загрузка данных' })
    }
    const reliefOk = hasSuccessfulJob(projectId, 'relief') || sourceSatisfied(sources?.dsm_source)
    if (!reliefOk) {
      missing.push({ layer: 'ЦММ', tab: 'Рельеф' })
    }
  } else if (module === 'water') {
    // Вода считается нейросетью по ортофотоплану: без АФС считать нечего,
    // от сессий «Рельефа» модуль не зависит.
    if (!hasAfs(projectId)) {
      missing.push({ layer: 'АФС', tab: 'Загрузка данных' })
    }
  }

  return { ok: missing.length === 0, missing }
}