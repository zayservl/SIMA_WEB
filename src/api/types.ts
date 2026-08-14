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

// 'custom' — пользовательские настройки: значения берутся не из пресета, а из
// явных полей (smoothing.* для сглаживания, output_resolution_m для разрешения).
export type SmoothingPreset = 'light' | 'medium' | 'strong' | 'custom'
export type ResolutionPreset = 'native' | '0.1m' | '0.25m' | '0.5m' | '1m' | '2m' | 'custom'

export interface ReliefSource {
  kind: 'system' | 'upload'
  system_session_id?: string
  upload_path?: string
}

export interface LoggingCategoryTable {
  rows: {
    category: string
    height: number
    slope: number
    density: number
  }[]
}

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
  /** Система высот. Может быть частью составной СК или отсутствовать в метаданных. */
  vertical_crs?: string
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
  /** Система высот. Может быть частью составной СК или отсутствовать в метаданных. */
  vertical_crs?: string
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
  session_id?: string
  tiles_total: number
  tiles_done: number
  tiles_failed: number
  tiles_skipped: number
  failed_tiles: FailedTile[]
  tiles: Tile[]
  started_at?: string
  finished_at?: string
  output_dir?: string
  params: ReliefParams | ForestParams | WaterParams
  recompute_of?: string
}

// ---- Параметры: Рельеф (#8,9,10,14) --------------------------------------

// 'las_class' — земля берётся из готовой классификации LAS (ASPRS class 2),
// собственная классификация не выполняется (backend: CheckClassification.is_ground).
export type FilterMethod = 'manual' | 'stat' | 'range' | 'kmeans' | 'smrf' | 'las_class'

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
  smoothing_preset: SmoothingPreset
  output_resolution_preset: ResolutionPreset
  /** Разрешение выходного файла, м/пиксель. Действует при output_resolution_preset='custom'. */
  output_resolution_m: number
  /**
   * ЦММ (цифровая модель местности, DSM) — второй основной выход «Рельефа»
   * наряду с ЦМР. Поля 1:1 к sima_relief_service.contract.DsmParams: сервис
   * строит ЦММ только при enabled=true (шаг 3b). ЦММ — вход модуля «Древостой».
   */
  dsm: {
    enabled: boolean
    output_type: 'max' | 'mean' | 'idw'
    interpolate: boolean
    fill_holes: boolean
    max_search_distance: number
    edge_extrapolation_m: number
  }
  derivatives: {
    slopes: boolean
    slopes_res: number
    aspect: boolean
    aspect_res: number
    tpi: boolean
    tpi_res: number
    tpi_radii: number[]
    /**
     * Интерполяция и экстраполяция ЦМР — заполнение пустот перед расчётом
     * производных (backend: step_dtm → FillConfig). Общие для всех выходов.
     */
    interpolation: boolean
    inter_amp: number
    /** Допустимая экстраполяция ЦМР за границу валидной области, м (0 — только внутренние дыры). */
    edge_extrapolation_m: number
    /** Интерполяция и экстраполяция карты уклонов — задаются независимо от ЦМР. */
    slopes_interpolation: boolean
    slopes_inter_amp: number
    slopes_edge_extrapolation_m: number
    /** Интерполяция и экстраполяция карты экспозиций — задаются независимо от ЦМР. */
    aspect_interpolation: boolean
    aspect_inter_amp: number
    aspect_edge_extrapolation_m: number
  }
  heights: {
    enabled: boolean
    source: 'las' | 'dem'
    /** Минимальное расстояние между точками отметок, м (пространственное прореживание). */
    min_distance_m: number
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

// Способ определения параметров блока: моделью (ИИ) или явными правилами.
// В режиме 'ai' ручные пороги блока не задаются — их подбирает модель.
export type ParamMode = 'ai' | 'algorithmic'

export interface ForestParams {
  cmd: {
    enabled: boolean
    mode: ParamMode
    threshold_surface: number
    threshold_shrub: number
    channels: { chm: boolean }
    median_window: number
  }
  detection: {
    /** Детекция крон — опциональный расчёт; от неё зависят статистики по сегментам. */
    enabled: boolean
    mode: ParamMode
    vegetation_state: 'active' | 'absent'
    /**
     * Окно поиска вершин крон, м (backend: sima_forest_cmd.detect_tree_tops.window_m).
     * Задаёт минимальное расстояние между соседними деревьями и потому напрямую
     * определяет их найденное число — без этого параметра результат невоспроизводим.
     * Значение переводится в радиус ядра в пикселях, поэтому фактический поперечник
     * окна равен `2 * round(peak_size_m / res) * res + res`: при 1 м это 2.5 м на
     * сетке 0.5 м и 3.0 м на сетке 1 м. Легаси СИМА 1.44: 1 м.
     */
    peak_size_m: number
  }
  stats: {
    enabled: boolean
    percentiles: number[]
    vci_step: number
    metrics: string[]
  }
  /** Экспертные параметры сглаживания — действуют при smoothing_preset='custom'. */
  smoothing: {
    sigma: number
    order: number
    window: number
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
    table: LoggingCategoryTable
  }
  smoothing_preset: SmoothingPreset
  output_resolution_preset: ResolutionPreset
  /**
   * Цифровая модель местности (ЦММ) из сессии «Рельефа».
   *
   * Для расчёта ЦМД не требуется: ЦМД строится отдельным проходом по облаку
   * (`filters.hag_delaunay` нормализует высоты относительно земли), поэтому не
   * зависит ни от ЦММ, ни от абсолютного уровня высот — облако в ТЛО и облако в
   * абсолютных отметках дают один результат. Поле остаётся для слоёв, которым
   * ЦММ нужна сама по себе.
   */
  dsm_source: ReliefSource
  /**
   * Производные рельефа. Отдельного выбора в интерфейсе нет: источник
   * подставляется автоматически из той же сессии, что и ЦММ.
   */
  derivatives_source: ReliefSource
}

// ---- Параметры: Вода (#15) -----------------------------------------------
// Единственный вход модуля — АФС проекта: маска воды строится нейросетью по
// ортофотоплану. ЦМР, ЦМД и производные рельефа в цепочке «Воды» не участвуют,
// поэтому от сессии «Рельефа» модуль не зависит.

export interface WaterParams {
  segment: {
    /** Порог уверенности модели: 0.01…1 с шагом 0.01. */
    threshold: number
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