import type { Job, OutputArtifact, Project, Tile } from '@/api/types'

// Каталог сессии: results/<project_id>/<job_type>/session-<session_id>.
// При повторном запуске тайла создаётся новый tile.id → новая вложенная папка,
// старые выходные данные не перезаписываются (требование заказчика).
export function sessionDir(job: Job, project?: Project): string {
  const pid = project?.id ?? job.project_id
  const sid = job.session_id ?? 'unknown'
  return `results/${pid}/${job.type}/session-${sid}`
}

// Каталог конкретного тайла внутри сессии.
export function tileDir(job: Job, tile: Tile, project?: Project): string {
  return `${sessionDir(job, project)}/${tile.id}`
}

// Псевдо-стабильный размер по имени (без Math.random — детерминированно).
function sizeFrom(seed: string, base: number, spread: number): number {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return +(base + (h % 100) / 100 * spread).toFixed(1)
}

// Список выходных артефактов по типу задачи. Соответствует модулям ТЗ
// (Рельеф/Древостой/Вода) и согласованным форматам: GeoTIFF/BigTIFF/LAS/Shapefile.
function artifactDefs(type: Job['type']): { name: string; kind: OutputArtifact['kind']; format: OutputArtifact['format']; base: number; spread: number }[] {
  switch (type) {
    case 'relief':
      return [
        { name: 'dsm.tif', kind: 'raster', format: 'GeoTIFF', base: 8, spread: 6 },
        { name: 'dsm_smoothed.tif', kind: 'raster', format: 'GeoTIFF', base: 6, spread: 4 },
        { name: 'slopes.tif', kind: 'raster', format: 'GeoTIFF', base: 4, spread: 3 },
        { name: 'aspect.tif', kind: 'raster', format: 'GeoTIFF', base: 4, spread: 3 },
        { name: 'tpi.tif', kind: 'raster', format: 'GeoTIFF', base: 5, spread: 3 },
        { name: 'heights.shp', kind: 'vector', format: 'Shapefile', base: 0.3, spread: 0.4 },
      ]
    case 'forest':
      return [
        { name: 'chm.tif', kind: 'raster', format: 'GeoTIFF', base: 10, spread: 6 },
        { name: 'its.tif', kind: 'raster', format: 'GeoTIFF', base: 8, spread: 5 },
        { name: 'den.tif', kind: 'raster', format: 'GeoTIFF', base: 8, spread: 5 },
        { name: 'crowns.shp', kind: 'vector', format: 'Shapefile', base: 1.2, spread: 0.8 },
        { name: 'trees.shp', kind: 'vector', format: 'Shapefile', base: 0.8, spread: 0.6 },
        { name: 'trees.las', kind: 'point-cloud', format: 'LAS', base: 40, spread: 30 },
      ]
    case 'water':
      return [
        { name: 'water.shp', kind: 'vector', format: 'Shapefile', base: 0.6, spread: 0.5 },
        { name: 'swamp.shp', kind: 'vector', format: 'Shapefile', base: 0.4, spread: 0.3 },
        { name: 'buffers.shp', kind: 'vector', format: 'Shapefile', base: 0.3, spread: 0.2 },
      ]
  }
}

let artSeq = 0
function nextArtId(): string {
  artSeq += 1
  return 'a-' + artSeq.toString(36)
}

// Сгенерировать выходные артефакты тайла (вызывается по завершении тайла).
export function artifactsFor(job: Job, tile: Tile, project?: Project): OutputArtifact[] {
  const dir = tileDir(job, tile, project)
  return artifactDefs(job.type).map((d) => ({
    id: nextArtId(),
    name: d.name,
    kind: d.kind,
    format: d.format,
    size_mb: sizeFrom(tile.id + d.name, d.base, d.spread),
    path: `${dir}/${d.name}`,
  }))
}

// Суммарный объём выходных артефактов задачи (МБ).
export function totalOutputSize(job: Job): number {
  return job.tiles.reduce((acc, t) => acc + (t.output_files || []).reduce((a, f) => a + f.size_mb, 0), 0)
}

// Оценка объёма промежуточных/временных файлов (раздувание диска, встреча 00:54:55).
export function tempFilesSize(job: Job): number {
  // Эмпирически ~3-5x от объёма результата для несжатых промежуточных GeoTIFF.
  const out = totalOutputSize(job)
  const tilesActive = job.tiles.filter((t) => t.status === 'running' || t.status === 'done').length
  return +(out * 0.6 + tilesActive * 12).toFixed(1)
}

export interface LogLine {
  ts: string
  tile: string
  step: string
  status: 'done' | 'failed' | 'skipped'
  message?: string
  duration_ms?: number
}

// Сборка лога задачи по шагам тайлов (встреча: «метку времени для каждого шага»).
export function jobLog(job: Job): LogLine[] {
  const lines: LogLine[] = []
  for (const t of job.tiles) {
    for (const s of t.steps) {
      if (s.status === 'pending' || s.status === 'running') continue
      lines.push({
        ts: s.finished_at || s.started_at || '',
        tile: t.name,
        step: s.name,
        status: s.status as 'done' | 'failed' | 'skipped',
        message: s.message,
        duration_ms: s.duration_ms,
      })
    }
  }
  return lines.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0))
}