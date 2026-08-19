// Каталог входных тайлов проекта — то, что «Загрузка данных» считала из
// каталогов АФС/ВЛС. Живёт в сторе, а не в стейте страницы: вкладки расчётов
// выбирают из этого списка тайлы, отправляемые на расчёт.

export interface InputAfs {
  file: string
  crs: string
  vertical_crs?: string
  resolution_m: number
  size_mb: number
  /** Нижний левый угол тайла в его СК, [x, y]. */
  origin: [number, number]
}

export interface InputVls {
  file: string
  crs: string
  vertical_crs?: string
  density_pts_m2: number
  height_range_m: [number, number]
  size_mb: number
  /** Классы ASPRS, присутствующие в файле. Пустой массив — классификации нет. */
  classes: number[]
  /** Нижний левый угол тайла в его СК, [x, y]. */
  origin: [number, number]
}

export interface InputTile {
  id: string
  name: string // общий номер пары, напр. tile_001
  afs: InputAfs | null
  vls: InputVls | null
  area_km2: number
}

/** Режим работы проекта: задаётся тем, какие каталоги указаны. */
export type InputMode = 'pair' | 'vls-only' | 'afs-only'

export const TARGET_CRS = 'EPSG:32637'
export const VERTICAL_CRS = 'EPSG:5705 (Балтийская 1977)'

// Классы ASPRS, используемые конвейером: 2 — земля (вход «Рельефа»),
// 3-5 — растительность (вход «Древостоя»), 7 — шум.
export const CLASS_LABELS: Record<number, string> = {
  1: 'не классифицировано',
  2: 'земля',
  3: 'низкая растительность',
  4: 'средняя растительность',
  5: 'высокая растительность',
  6: 'здания',
  7: 'шум',
}

// Демо-набор пар ТИФ+ЛАС. Включает: совпадающие пары, пары с несовпадением СК
// (демонстрация приведения), пару без ВЛС (неполная), файлы с классификацией и без.
export function generateMockInputTiles(mode: InputMode): InputTile[] {
  const tiles: InputTile[] = []
  for (let i = 1; i <= 24; i++) {
    const id = `in-${String(i).padStart(3, '0')}`
    const name = `tile_${String(i).padStart(3, '0')}`
    const afsFile = `${String(i * 100).padStart(6, '0')}.tif`
    const vlsFile = `pt${String(i * 100).padStart(6, '0')}.las`
    const afsSize = 130 + ((i * 7) % 30)
    const vlsSize = 115 + ((i * 5) % 25)
    const density = 4000 + ((i * 37) % 1000)
    const hMin = +(15 + ((i * 0.5) % 30)).toFixed(2)
    const hMax = +(950 + ((i * 3) % 200)).toFixed(2)
    // Сетка тайлов 1×1 км: шесть в ряду, начало съёмки — условная точка в UTM.
    const origin: [number, number] = [
      414000 + ((i - 1) % 6) * 1000,
      6188000 + Math.floor((i - 1) / 6) * 1000,
    ]

    let afsCrs = TARGET_CRS
    // Часть файлов приходит уже классифицированной, часть — сырой.
    const classes = i % 3 === 0 ? [] : [1, 2, 3, 4, 5]
    let vls: InputVls | null = {
      file: vlsFile, crs: TARGET_CRS, vertical_crs: VERTICAL_CRS,
      density_pts_m2: density, height_range_m: [hMin, hMax], size_mb: vlsSize,
      classes, origin,
    }
    // Система высот в метаданных АФС встречается не всегда.
    let afs: InputAfs | null = {
      file: afsFile, crs: afsCrs, vertical_crs: i % 4 === 0 ? undefined : VERTICAL_CRS,
      resolution_m: 0.14, size_mb: afsSize, origin,
    }

    if (mode === 'vls-only') {
      afs = null
    } else if (mode === 'afs-only') {
      vls = null
    } else if (i === 21 || i === 22) {
      // СК не совпадает внутри пары → будет приведена к СК АФС
      afsCrs = 'EPSG:4326'
      afs = { ...afs!, crs: afsCrs, origin: [37.61, 55.75] }
    } else if (i === 17 || i === 18) {
      // Геопривязка ВЛС смещена относительно АФС при совпадающей СК
      vls = { ...vls!, origin: [origin[0] + 2.5, origin[1] - 1.75] }
    } else if (i === 23) {
      // Неполная пара: нет ВЛС
      vls = null
    }

    tiles.push({ id, name, area_km2: 1.0, afs, vls })
  }
  return tiles
}

/** Режим проекта по составу каталога тайлов. */
export function inputMode(tiles: InputTile[]): InputMode {
  const hasAfs = tiles.some((t) => t.afs)
  const hasVls = tiles.some((t) => t.vls)
  if (hasAfs && !hasVls) return 'afs-only'
  if (!hasAfs && hasVls) return 'vls-only'
  return 'pair'
}

/**
 * Расхождение геопривязки внутри пары: расстояние между нижними левыми углами
 * тайлов АФС и ВЛС, м. Считается только при совпадающих СК — при разных СК
 * координаты несопоставимы, и пара сначала приводится к целевой СК.
 * null — сверять нечего.
 */
export function originOffsetM(t: InputTile): number | null {
  if (!t.afs || !t.vls || t.afs.crs !== t.vls.crs) return null
  const dx = t.afs.origin[0] - t.vls.origin[0]
  const dy = t.afs.origin[1] - t.vls.origin[1]
  return +Math.hypot(dx, dy).toFixed(2)
}

/** Допуск на расхождение углов по умолчанию, м. */
export const DEFAULT_ORIGIN_TOLERANCE_M = 1

/** Координаты угла для вывода в интерфейсе. */
export function formatOrigin(origin: [number, number]): string {
  return `${origin[0].toFixed(2)}, ${origin[1].toFixed(2)}`
}
