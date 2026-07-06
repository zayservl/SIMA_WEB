// ============================================================================
// Контракты API «СИМА» — типы, готовые к подключению реального FastAPI-бэкенда.
// Моки (src/mocks) возвращают те же типы. При переходе на реальный бэкенд
// меняется только реализация fetch-обёрток в src/api/*.ts.
// ============================================================================

// ---- Проекты/Сцены -------------------------------------------------------

export interface Project {
  id: string
  name: string
  created_at: string
  updated_at: string
  status: ProjectStatus
  scene: Scene
}

export type ProjectStatus = 'empty' | 'uploaded' | 'processing' | 'done' | 'error'

export interface Scene {
  id: string
  afs_dir?: string
  vls_dir?: string
  target_crs?: string
  reproject: boolean
  deterministic: boolean
  seed: number
}

// ---- Оценка исходных материалов (#5, #6) --------------------------------

export interface MaterialAssessment {
  afs: AfsReport | null
  vls: VlsReport | null
}

export interface AfsReport {
  crs: string
  extent_area_km2: number
  resolution_m: number
  ofp_scale: string
  tiles_total: number
  tiles_ok: number
  tiles_failed: number
  failed_tiles: FailedTile[]
}

export interface VlsReport {
  crs: string
  extent_area_km2: number
  density_pts_m2: number
  tlo_scale: string
  tlo_height_range_m: [number, number]
  tiles_total: number
  tiles_ok: number
  tiles_failed: number
  failed_tiles: FailedTile[]
}

export interface FailedTile {
  name: string
  reason: string
}

// ---- Задачи (#4) ---------------------------------------------------------

export type JobType = 'relief' | 'forest' | 'water'
export type JobStatus = 'queued' | 'running' | 'success' | 'failed' | 'cancelled'

// ---- Тайл внутри задачи (#4: статус по каждому тайлу) --------------------

export type TileStatus = 'queued' | 'running' | 'done' | 'failed' | 'skipped'
export type TileKind = 'afs' | 'vls' | 'pair'

export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

// Один шаг алгоритма внутри тайла (фильтрация → ЦМР → производные → …).
// Метки времени по шагам — требование встречи («метку времени для каждого
// из шагов, чтобы оценивать, где работал, когда»).
export interface TileStep {
  name: string
  status: StepStatus
  started_at?: string
  finished_at?: string
  duration_ms?: number
  message?: string // лог-строка / причина сбоя шага
}

// Потайловое состояние. id уникален в рамках сессии; при повторном запуске
// тайла создаётся новый Tile с новым id (старые выходные данные не затираются).
export interface Tile {
  id: string
  name: string
  kind: TileKind
  status: TileStatus
  steps: TileStep[]
  current_step?: string
  started_at?: string
  finished_at?: string
  duration_ms?: number
  reason?: string // причина сбоя (для failed)
  retry_of?: string // id исходного тайла, если это повторный запуск
  output_dir?: string // куда сохранены данные тайла (Блок Г)
  output_files?: OutputArtifact[] // выходные артефакты тайла (Блок Г)
}

export interface Job {
  id: string
  project_id: string
  type: JobType
  status: JobStatus
  progress: number
  session_id?: string // генерируется стором при addJob
  tiles_total: number
  tiles_done: number
  tiles_failed: number
  tiles_skipped: number
  failed_tiles: FailedTile[]
  tiles: Tile[]
  started_at?: string
  finished_at?: string
  output_dir?: string // корневой каталог сессии: results/<project>/<type>/session-<id> (Блок Г)
  params: ReliefParams | ForestParams | WaterParams
}

// ---- Параметры: Рельеф (#8,9,10,14) --------------------------------------

export type FilterMethod = 'manual' | 'stat' | 'range' | 'kmeans' | 'smrf'

export interface ReliefParams {
  filter_method: FilterMethod
  filter: {
    spm_min?: number
    spm_max?: number
    spr_num?: number
    spp_min?: number
    spp_max?: number
    mean_k?: number
    mult?: number
  }
  smrf: {
    slope: number
    window: number
    threshold: number
    scalar: number
    cut_smrf: boolean
    elm: boolean
    outlier: boolean
  }
  smoothing: {
    enabled: boolean
    sigma: number
    order: number
    window: number
  }
  derivatives: {
    slopes: boolean
    slopes_res: number
    aspect: boolean
    aspect_res: number
    tpi: boolean
    tpi_radii: number[]
    interpolation: boolean
    inter_amp: number
  }
  heights: {
    enabled: boolean
    source: 'las' | 'dem'
    step: number
  }
  vectors: {
    horizontals: number[]
    tin: boolean
  }
  target_crs: string
  deterministic: boolean
  seed: number
}

// ---- Параметры: Лес/Древостой (#11,12,13,16) -----------------------------

export interface ForestParams {
  cmd: {
    enabled: boolean
    threshold_surface: number
    threshold_shrub: number
    channels: { chm: boolean; its: boolean; den: boolean }
    median_window: number
  }
  detection: {
    method: 'yolov5' | 'watershed' | 'both'
    sample_size: number
    bound: number
    season: 'summer' | 'winter'
  }
  stats: {
    enabled: boolean
    percentiles: number[]
    vci_step: number
    metrics: string[]
  }
  logging_category: {
    enabled: boolean
    algorithm: 'threshold' | 'linear'
    features: string[]
    thresholds?: {
      hght: number
      dist_far: number
      dist_near: number
      diam: number
    }
  }
  extras: {
    fire: boolean
    fire_res: number
    fire_sm: number
    wind: boolean
    wind_res: number
    wind_sm: number
    tlo: boolean
    peaks: boolean
    peak_size: number
  }
}

// ---- Параметры: Вода (#15) -----------------------------------------------

export interface WaterParams {
  segment: {
    threshold: number
    sample_size: number
    bound: number
    smooth: number
    resolution: number
  }
  swamp: {
    segment: boolean
    threshold: number
    smooth: number
    resolution: number
    classify: boolean
  }
  buffers: {
    coastal_m: number
    protective_m: number
    water_protection_m: number
  }
}

// ---- Выходные артефакты (Блок Г) -----------------------------------------
// Заменяет прежние контракты визуализации (LayerKind/ResultLayer) на модель
// «файлы результата по тайлам» — без карты, только данные и архивы.

export type ArtifactFormat = 'GeoTIFF' | 'BigTIFF' | 'LAS' | 'Shapefile' | 'CSV'
export type ArtifactKind = 'raster' | 'vector' | 'point-cloud'

export interface OutputArtifact {
  id: string
  name: string // имя файла, напр. dsm.tif
  kind: ArtifactKind
  format: ArtifactFormat
  size_mb: number
  path: string // полный путь внутри каталога сессии
}

// ---- Глобальные настройки ------------------------------------------------

export interface GlobalSettings {
  model_paths: {
    treecanopy: string
    water: string
    swamp: string
    forest: string
  }
  data_dir: string
  results_dir: string
  default_season: 'summer' | 'winter'
  default_satellite: string
  default_target_crs: string
  deterministic: {
    enabled: boolean
    seed: number
    cudnn_deterministic: boolean
    cudnn_benchmark: boolean
    num_workers: number
  }
}