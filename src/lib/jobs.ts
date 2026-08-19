import type { Job, JobType } from '@/api/types'

const TYPE_LABEL: Record<JobType, string> = { relief: 'Рельеф', forest: 'Древостой', water: 'Вода' }

/**
 * Имя расчёта по умолчанию — «<Модуль> N», где N продолжает нумерацию расчётов
 * этого модуля в проекте. Пользователь правит его при запуске и в очереди задач.
 */
export function defaultJobName(type: JobType, jobs: Job[], projectId: string): string {
  const n = jobs.filter((j) => j.project_id === projectId && j.type === type).length + 1
  return `${TYPE_LABEL[type]} ${n}`
}
