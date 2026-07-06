import type { JobType, Tile, TileKind, TileStep } from '@/api/types'

// Шаги алгоритма по типу задачи — используются для прогресса внутри тайла
// и для лога по шагам (встреча: «метку времени для каждого из шагов»).
export const JOB_STEPS: Record<JobType, string[]> = {
  relief: ['Фильтрация облака точек', 'ЦМР (интерполяция)', 'Сглаживание', 'Уклоны / экспозиции', 'TPI', 'Высоты'],
  forest: ['ЦМР крон (CHM/ITS/DEN)', 'Сегментация крон', 'Детекция деревьев', 'Статистики по сегментам', 'Категория рубки'],
  water: ['Сегментация воды', 'Болота', 'Охранные зоны / буферы'],
}

// Расширение файла и тип тайла по типу задачи.
export const TILE_EXT: Record<JobType, string> = { relief: 'tif', forest: 'las', water: 'tif' }
export const TILE_KIND: Record<JobType, TileKind> = { relief: 'pair', forest: 'pair', water: 'afs' }

const STEPS_TEMPLATE = (type: JobType): TileStep[] =>
  JOB_STEPS[type].map((name) => ({ name, status: 'pending' as const }))

let tileSeq = 0
function nextTileId(): string {
  tileSeq += 1
  return 't-' + tileSeq.toString(36).padStart(4, '0') + '-' + Math.random().toString(36).slice(2, 6)
}

// Имя файла тайла по порядковому номеру (1-based).
export function tileName(type: JobType, indexOneBased: number): string {
  return `tile_${String(indexOneBased).padStart(3, '0')}.${TILE_EXT[type]}`
}

// Создать начальный список тайлов для задачи (все в статусе queued).
export function generateTiles(type: JobType, count: number): Tile[] {
  const tiles: Tile[] = []
  for (let i = 1; i <= count; i++) {
    tiles.push({
      id: nextTileId(),
      name: tileName(type, i),
      kind: TILE_KIND[type],
      status: 'queued',
      steps: STEPS_TEMPLATE(type),
    })
  }
  return tiles
}

// Создать «повторный» тайл: новый id, ссылка на исходный, шаги сброшены.
export function makeRetryTile(source: Tile, type: JobType): Tile {
  return {
    id: nextTileId(),
    name: source.name,
    kind: source.kind,
    status: 'queued',
    steps: STEPS_TEMPLATE(type),
    retry_of: source.id,
  }
}

let sessionSeq = 0
export function newSessionId(): string {
  sessionSeq += 1
  return 's-' + sessionSeq.toString(36).padStart(4, '0') + '-' + Math.random().toString(36).slice(2, 6)
}