import type { Job, JobType } from '@/api/types'
import type { InputTile } from '@/lib/inputTiles'

const TYPE_LABEL: Record<JobType, string> = { relief: 'Рельеф', forest: 'Древостой', water: 'Вода' }

/**
 * Имя расчёта по умолчанию — «<Модуль> N», где N продолжает нумерацию расчётов
 * этого модуля в проекте. Пользователь правит его при запуске и в очереди задач.
 */
export function defaultJobName(type: JobType, jobs: Job[], projectId: string): string {
  const n = jobs.filter((j) => j.project_id === projectId && j.type === type).length + 1
  return `${TYPE_LABEL[type]} ${n}`
}

/**
 * Тайл в списке выбора на вкладке расчёта. Недоступные не исчезают из списка,
 * а показываются с причиной: пользователь должен видеть, что тайл загружен, но
 * посчитать его нечем.
 */
export interface RunTile {
  name: string
  available: boolean
  reason?: string
}

/** Какие входные материалы нужны модулю, чтобы тайл вообще можно было считать. */
const REQUIRED_INPUT: Record<JobType, 'vls' | 'afs'> = {
  relief: 'vls',
  forest: 'vls',
  water: 'afs',
}

/**
 * Список тайлов проекта в разрезе одного модуля: что доступно к расчёту, а что
 * нет и почему. «Рельеф» и «Древостой» считаются по облаку точек, «Вода» — по
 * ортофотоплану, поэтому недостающий материал сразу снимает тайл с расчёта.
 */
export function moduleRunTiles(type: JobType, tiles: InputTile[]): RunTile[] {
  const need = REQUIRED_INPUT[type]
  return tiles.map((t) => {
    const has = need === 'vls' ? !!t.vls : !!t.afs
    return has
      ? { name: t.name, available: true }
      : { name: t.name, available: false, reason: need === 'vls' ? 'нет ВЛС' : 'нет АФС' }
  })
}

/** Имена доступных к расчёту тайлов — начальный выбор «все». */
export function availableNames(runTiles: RunTile[]): string[] {
  return runTiles.filter((t) => t.available).map((t) => t.name)
}
