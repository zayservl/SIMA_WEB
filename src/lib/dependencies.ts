// Проверка зависимостей модулей СИМА v2.
// Чистая функция (не использует хуки React) — обращается к store через getState().
// Используется страницами Forest/Water для блокировки запуска при отсутствии
// необходимых входных данных (assessment / предыдущих задач).

import { useProjectStore } from '@/store/projectStore'
import type { JobType } from '@/api/types'

export interface DependencyCheck {
  ok: boolean
  missing: { layer: string; tab: string }[]
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

export function checkDependencies(projectId: string, module: JobType): DependencyCheck {
  const missing: { layer: string; tab: string }[] = []

  if (module === 'relief') {
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
  } else if (module === 'forest') {
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
    if (!hasSuccessfulJob(projectId, 'relief')) {
      missing.push({ layer: 'ЦМР (Рельеф)', tab: 'Рельеф' })
    }
  } else if (module === 'water') {
    if (!hasAssessment(projectId)) {
      missing.push({ layer: 'АФС + ВЛС', tab: 'Загрузка данных' })
    }
    if (!hasSuccessfulJob(projectId, 'forest')) {
      missing.push({ layer: 'ЦМД (Древостой)', tab: 'Древостой' })
    }
  }

  return { ok: missing.length === 0, missing }
}