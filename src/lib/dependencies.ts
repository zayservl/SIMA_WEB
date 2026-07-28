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

// Источники, которые могут закрывать зависимость модуля от предыдущего расчёта
// (Forest: ЦМР/производные рельефа; Water: ЦМД) — либо выбором в системе, либо
// загрузкой пользовательского .geotiff, минуя предыдущий модуль целиком.
export interface DependencySources {
  dsm_source?: ReliefSource
  derivatives_source?: ReliefSource
  cmd_source?: ReliefSource
}

// Проверка, что у проекта загружены исходные материалы (АФС + ВЛС).
function hasAssessment(projectId: string): boolean {
  const { assessment } = useProjectStore.getState()
  const a = assessment[projectId]
  return !!(a && a.afs && a.vls)
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
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
  } else if (module === 'forest') {
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
    const reliefOk =
      hasSuccessfulJob(projectId, 'relief') ||
      (sourceSatisfied(sources?.dsm_source) && sourceSatisfied(sources?.derivatives_source))
    if (!reliefOk) {
      missing.push({ layer: 'ЦМР (Рельеф)', tab: 'Рельеф' })
    }
  } else if (module === 'water') {
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
    const forestOk = hasSuccessfulJob(projectId, 'forest') || sourceSatisfied(sources?.cmd_source)
    if (!forestOk) {
      missing.push({ layer: 'ЦМД (Древостой)', tab: 'Древостой' })
    }
  }

  return { ok: missing.length === 0, missing }
}