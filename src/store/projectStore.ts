import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Project, Scene, MaterialAssessment, Job, ReliefParams, ForestParams, WaterParams, Tile } from '@/api/types'
import { generateTiles, newSessionId } from '@/lib/tiles'

// Параметры по умолчанию. «Рельеф» отдаёт полный набор выходов — ЦМР, ЦММ,
// TPI, уклоны и экспозиции включены изначально; сервис гейтит каждый шаг своим
// флагом (service.py::_run_tile), поэтому флаги остаются в контракте.
export const defaultReliefParams: ReliefParams = {
  filter_method: 'smrf',
  filter: { spm_min: 0, spm_max: 100, spr_num: 2, spp_min: 1, spp_max: 99, mean_k: 8, mult: 2 },
  smrf: { slope: 0.2, window: 16, threshold: 0.45, scalar: 1.2, cut_smrf: false, elm: true, outlier: true },
  smoothing: { enabled: true, sigma: 1.0, order: 0, window: 3 },
  smoothing_preset: 'medium',
  output_resolution_preset: 'native',
  output_resolution_m: 1,
  dsm: { enabled: true, output_type: 'max', interpolate: true, fill_holes: true, max_search_distance: 100, edge_extrapolation_m: 5 },
  derivatives: {
    slopes: true, slopes_res: 1,
    aspect: true, aspect_res: 1,
    tpi: true, tpi_res: 10, tpi_radii: [270, 810, 2430],
    // interpolation/inter_amp управляют заполнением пустот ЦМР (step_dtm →
    // FillConfig): значения выровнены с DerivativesParams бэкенда (True/100).
    interpolation: true, inter_amp: 100, edge_extrapolation_m: 5,
    // Уклоны и экспозиции интерполируются независимо от ЦМР — по умолчанию
    // повторяют её настройки.
    slopes_interpolation: true, slopes_inter_amp: 100, slopes_edge_extrapolation_m: 5,
    aspect_interpolation: true, aspect_inter_amp: 100, aspect_edge_extrapolation_m: 5,
  },
  heights: { enabled: false, source: 'las', min_distance_m: 10 },
  vectors: { horizontals: [0.5, 2, 5, 10], tin: false },
  target_crs: '',
  deterministic: true, seed: 42,
}

export const defaultForestParams: ForestParams = {
  cmd: { enabled: true, mode: 'algorithmic', threshold_surface: 0.5, threshold_shrub: 5, channels: { chm: true }, median_window: 3 },
  detection: { enabled: true, mode: 'ai', vegetation_state: 'active' },
  stats: { enabled: true, percentiles: [50, 55, 60, 65, 70, 75, 80, 85, 90, 95], vci_step: 1, metrics: ['entropy', 'max', 'mean', 'std', 'skew', 'kurtosis', 'vci', 'area', 'percentiles'] },
  logging_category: {
    enabled: true,
    algorithm: 'threshold',
    features: ['dist', 'diam', 'hght'],
    thresholds: { hght: 5, dist_far: 10, dist_near: 4, diam: 16 },
    table: {
      rows: [
        { category: '1 категория', height: 8, slope: 15, density: 0.3 },
        { category: '2 категория', height: 12, slope: 10, density: 0.5 },
        { category: '3 категория', height: 16, slope: 7, density: 0.7 },
        { category: '4 категория', height: 20, slope: 5, density: 0.9 },
      ],
    },
  },
  smoothing_preset: 'medium',
  smoothing: { sigma: 1.0, order: 0, window: 3 },
  output_resolution_preset: 'native',
  dsm_source: { kind: 'system' },
  derivatives_source: { kind: 'system' },
}

export const defaultWaterParams: WaterParams = {
  segment: { threshold: 0.7 },
}

interface ProjectStore {
  projects: Project[]
  assessment: Record<string, MaterialAssessment>
  jobs: Job[]
  createProject: (name: string) => Project
  updateProject: (projectId: string, patch: Partial<Project>) => void
  updateScene: (projectId: string, patch: Partial<Scene>) => void
  setAssessment: (projectId: string, a: MaterialAssessment) => void
  addJob: (job: Job) => void
  updateJob: (jobId: string, patch: Partial<Job>) => void
  recomputeJob: (jobId: string, tileIds: string[] | undefined, newParams: ReliefParams | ForestParams | WaterParams) => void
  cancelJob: (jobId: string) => void
  stopTile: (jobId: string, tileId: string) => void
  removeProject: (id: string) => void
}

// Пересчёт агрегатов задачи по массиву тайлов.
function recompute(tiles: Tile[]): Pick<Job, 'tiles_done' | 'tiles_failed' | 'tiles_skipped' | 'failed_tiles' | 'progress'> {
  const done = tiles.filter((t) => t.status === 'done').length
  const failed = tiles.filter((t) => t.status === 'failed').length
  const skipped = tiles.filter((t) => t.status === 'skipped').length
  return {
    tiles_done: done,
    tiles_failed: failed,
    tiles_skipped: skipped,
    failed_tiles: tiles.filter((t) => t.status === 'failed').map((t) => ({ name: t.name, reason: t.reason || '' })),
    progress: 0, // будет пересчитан вызывающим с учётом tiles_total
  }
}

const demoProject: Project = {
  id: 'demo-001',
  name: 'Демо-участок 1',
  created_at: '2026-06-01T10:00:00Z',
  updated_at: '2026-07-01T12:00:00Z',
  status: 'done',
  scene: { id: 'scene-001', afs_dir: '/data/demo/afs', vls_dir: '/data/demo/vls', target_crs: '', reproject: true, deterministic: true, seed: 42 },
}

// Стор сохраняется в localStorage: без этого перезагрузка страницы (или
// прямой переход по URL) сбрасывает все посчитанные сессии Рельефа/Древостоя,
// и зависимые модули (Древостой/Вода) теряют возможность выбрать «Рассчитанную
// в системе» сессию, хотя задача была успешно завершена.
export const useProjectStore = create<ProjectStore>()(
  persist(
    (set) => ({
      projects: [demoProject],
      assessment: {
        'demo-001': {
          afs: {
            crs: '', extent_area_km2: 1.0, resolution_m: 0.14, ofp_scale: '1:1400',
            tiles_total: 1, tiles_ok: 1, tiles_failed: 0, failed_tiles: [],
          },
          vls: {
            crs: '', vertical_crs: 'EPSG:5705 (Балтийская 1977)',
            extent_area_km2: 1.0, density_pts_m2: 4577, tlo_scale: '1:500',
            tlo_height_range_m: [22.08, 1031.87],
            tiles_total: 1, tiles_ok: 1, tiles_failed: 0, failed_tiles: [],
          },
        },
      },
      jobs: [],
      createProject: (name) => {
        const p: Project = {
          id: 'p-' + Math.random().toString(36).slice(2, 9),
          name,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          status: 'empty',
          scene: { id: 's-' + Math.random().toString(36).slice(2, 9), reproject: true, deterministic: true, seed: 42 },
        }
        set((s) => ({ projects: [p, ...s.projects] }))
        return p
      },
      updateProject: (projectId, patch) =>
        set((s) => ({
          projects: s.projects.map((p) => (p.id === projectId ? { ...p, ...patch, updated_at: new Date().toISOString() } : p)),
        })),
      updateScene: (projectId, patch) =>
        set((s) => ({
          projects: s.projects.map((p) =>
            p.id === projectId ? { ...p, scene: { ...p.scene, ...patch }, updated_at: new Date().toISOString() } : p,
          ),
        })),
      setAssessment: (projectId, a) => set((s) => ({ assessment: { ...s.assessment, [projectId]: a } })),
      addJob: (job) =>
        set((s) => {
          // Нормализуем задачу: гарантированно есть tiles[], tiles_skipped, session_id.
          const normalized: Job = {
            ...job,
            session_id: job.session_id ?? newSessionId(),
            tiles_skipped: job.tiles_skipped ?? 0,
            tiles: job.tiles && job.tiles.length > 0 ? job.tiles : generateTiles(job.type, job.tiles_total),
          }
          return { jobs: [normalized, ...s.jobs] }
        }),
      updateJob: (jobId, patch) =>
        set((s) => ({ jobs: s.jobs.map((j) => (j.id === jobId ? { ...j, ...patch } : j)) })),
      recomputeJob: (jobId, tileIds, newParams) =>
        set((s) => {
          const src = s.jobs.find((j) => j.id === jobId)
          if (!src) return s
          const selectedTiles = tileIds
            ? src.tiles.filter((t) => tileIds.includes(t.id))
            : src.tiles
          const newTiles: Tile[] = selectedTiles.map((t) => ({
            id: 't-' + Math.random().toString(36).slice(2, 10),
            name: t.name,
            kind: t.kind,
            status: 'queued' as const,
            steps: t.steps.map((st) => ({ ...st, status: 'pending' as const, started_at: undefined, finished_at: undefined, duration_ms: undefined, message: undefined })),
            retry_of: t.id,
          }))
          const newJob: Job = {
            id: 'j-' + Math.random().toString(36).slice(2, 10),
            project_id: src.project_id,
            type: src.type,
            status: 'queued',
            progress: 0,
            session_id: newSessionId(),
            tiles_total: newTiles.length,
            tiles_done: 0,
            tiles_failed: 0,
            tiles_skipped: 0,
            failed_tiles: [],
            tiles: newTiles,
            params: newParams,
            recompute_of: jobId,
          }
          return { jobs: [newJob, ...s.jobs] }
        }),
      // Отмена расчёта. Уже посчитанные результаты сессии удаляются: сбрасываем
      // выходные каталоги и файлы у задачи и всех тайлов, счётчик готовых — в 0.
      // Тайлы, не успевшие упасть, помечаются пропущенными; упавшие сохраняют
      // причину сбоя — она нужна для разбора.
      cancelJob: (jobId) =>
        set((s) => ({
          jobs: s.jobs.map((j) => {
            if (j.id !== jobId || j.status === 'success' || j.status === 'cancelled') return j
            const ts = new Date().toISOString()
            const tiles = j.tiles.map((t) =>
              t.status === 'failed'
                ? { ...t, output_dir: undefined, output_files: undefined }
                : {
                    ...t,
                    status: 'skipped' as const,
                    current_step: undefined,
                    finished_at: t.finished_at ?? ts,
                    output_dir: undefined,
                    output_files: undefined,
                    steps: t.steps.map((st) =>
                      st.status === 'running' || st.status === 'pending'
                        ? { ...st, status: 'skipped' as const, finished_at: st.finished_at ?? ts }
                        : st,
                    ),
                  },
            )
            const agg = recompute(tiles)
            return {
              ...j, tiles, ...agg,
              status: 'cancelled' as const,
              progress: 0,
              finished_at: ts,
              output_dir: undefined,
            }
          }),
        })),
      stopTile: (jobId, tileId) =>
        set((s) => ({
          jobs: s.jobs.map((j) => {
            if (j.id !== jobId) return j
            const ts = new Date().toISOString()
            const tiles = j.tiles.map((t) => {
              if (t.id !== tileId || t.status !== 'running') return t
              return {
                ...t,
                status: 'skipped' as const,
                finished_at: ts,
                current_step: undefined,
                steps: t.steps.map((st) =>
                  st.status === 'running' ? { ...st, status: 'skipped' as const, finished_at: ts } : st
                ),
              }
            })
            const agg = recompute(tiles)
            const processed = agg.tiles_done + agg.tiles_failed + agg.tiles_skipped
            const hasActive = tiles.some((t) => t.status === 'running' || t.status === 'queued')
            return {
              ...j, tiles, ...agg,
              progress: Math.round((processed / j.tiles_total) * 100),
              status: hasActive ? j.status : ('cancelled' as const),
              finished_at: hasActive ? j.finished_at : ts,
            }
          }),
        })),
      removeProject: (id) => set((s) => ({ projects: s.projects.filter((p) => p.id !== id) })),
    }),
    {
      name: 'sima-project-store',
      partialize: (s) => ({ projects: s.projects, assessment: s.assessment, jobs: s.jobs }),
    },
  ),
)
