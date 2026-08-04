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

// Источники, которые могут закрывать зависимость модуля от предыдущего расчёта:
// Forest — ЦММ и производные рельефа, Water — ЦМР. Оба берутся из завершённых
// сессий «Рельефа», поэтому оба модуля зависят от него, а не друг от друга.
export interface DependencySources {
  dsm_source?: ReliefSource
  derivatives_source?: ReliefSource
  dem_source?: ReliefSource
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
      missing.push({ layer: 'ЦММ (Рельеф)', tab: 'Рельеф' })
    }
  } else if (module === 'water') {
    // Вода считается по АФС и ЦМР: «Древостой» в цепочке не участвует.
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
    const reliefOk = hasSuccessfulJob(projectId, 'relief') || sourceSatisfied(sources?.dem_source)
    if (!reliefOk) {
      missing.push({ layer: 'ЦМР (Рельеф)', tab: 'Рельеф' })
    }
  }

  return { ok: missing.length === 0, missing }
}