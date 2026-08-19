import type { Job, JobType, ReliefParams, TileStatus } from '@/api/types'
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

/**
 * Группировка «тайл → причина» по причине: список из полутора десятков строк
 * «сбой: PDAL пустой файл» по одной на тайл нечитаем, а сгруппированный —
 * сразу показывает, что именно пошло не так и на скольких тайлах.
 */
export function groupByReason(items: { name: string; reason?: string }[]): [string, string[]][] {
  const acc = new Map<string, string[]>()
  for (const it of items) {
    const key = it.reason ?? 'данных недостаточно'
    const names = acc.get(key)
    if (names) names.push(it.name)
    else acc.set(key, [it.name])
  }
  return [...acc.entries()]
}

// ---- Полнота сессии «Рельефа» как входа «Древостоя» ----------------------

const TILE_STATUS_REASON: Record<Exclude<TileStatus, 'done'>, string> = {
  failed: 'расчёт рельефа завершился сбоем',
  skipped: 'тайл пропущен',
  queued: 'тайл не считался',
  running: 'расчёт ещё идёт',
}

export interface ReliefCompleteness {
  /** Слои, не построенные во всей сессии: их отключили параметрами расчёта. */
  missingLayers: string[]
  /** Тайлы сессии без готового результата — с причиной по каждому. */
  incompleteTiles: { name: string; reason: string }[]
  /** Имена тайлов с полным результатом (без расширения файла). */
  readyTiles: string[]
}

/** Имя входного тайла из имени тайла задачи: tile_001.tif → tile_001. */
function baseName(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

/**
 * Разбор выбранной сессии «Рельефа» как источника данных для «Древостоя».
 * «Древостою» нужна ЦММ, а при включённой категоризации по уклону — ещё и карта
 * уклонов: сессия могла быть посчитана без них. Отдельно от этого часть тайлов
 * сессии могла не досчитаться — по ним данных нет независимо от набора слоёв.
 */
export function reliefCompleteness(job: Job | undefined, needSlopes: boolean): ReliefCompleteness {
  if (!job) return { missingLayers: [], incompleteTiles: [], readyTiles: [] }

  const params = job.params as ReliefParams
  const missingLayers: string[] = []
  if (!params.dsm?.enabled) missingLayers.push('ЦММ')
  if (needSlopes && !params.derivatives?.slopes) missingLayers.push('карта уклонов')

  const incompleteTiles: { name: string; reason: string }[] = []
  const readyTiles: string[] = []
  for (const t of job.tiles) {
    if (t.status === 'done') {
      readyTiles.push(baseName(t.name))
    } else {
      const base = TILE_STATUS_REASON[t.status]
      incompleteTiles.push({ name: baseName(t.name), reason: t.reason ? `${base}: ${t.reason}` : base })
    }
  }
  // Слоя нет во всей сессии — значит нет и по каждому её тайлу.
  if (missingLayers.length > 0) {
    const missing = `в сессии не построена ${missingLayers.join(', ')}`
    for (const name of readyTiles) incompleteTiles.push({ name, reason: missing })
    return { missingLayers, incompleteTiles, readyTiles: [] }
  }

  return { missingLayers, incompleteTiles, readyTiles }
}

/**
 * Список тайлов «Древостоя»: доступны только те, по которым выбранная сессия
 * «Рельефа» дала полный результат. Тайлы проекта, оставшиеся за пределами
 * сессии, показываются с причиной — иначе их молчаливое исчезновение из списка
 * выглядит как потеря данных.
 */
export function forestRunTiles(
  tiles: InputTile[],
  completeness: ReliefCompleteness,
  hasSession: boolean,
): RunTile[] {
  const reasonByName = new Map(completeness.incompleteTiles.map((t) => [t.name, t.reason]))
  const ready = new Set(completeness.readyTiles)

  return moduleRunTiles('forest', tiles).map((t) => {
    if (!t.available) return t
    if (!hasSession) return { ...t, available: false, reason: 'не выбрана сессия «Рельефа»' }
    if (ready.has(t.name)) return t
    return { ...t, available: false, reason: reasonByName.get(t.name) ?? 'тайла нет в сессии «Рельефа»' }
  })
}
