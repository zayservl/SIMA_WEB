import { create } from 'zustand'
import type { Project, Scene, MaterialAssessment, Job, ReliefParams, ForestParams, WaterParams, Tile } from '@/api/types'
import { generateTiles, makeRetryTile, newSessionId } from '@/lib/tiles'

// Демо-параметры по умолчанию (из текущего проекта)
export const defaultReliefParams: ReliefParams = {
  filter_method: 'smrf',
  filter: { spm_min: 0, spm_max: 100, spr_num: 2, spp_min: 1, spp_max: 99, mean_k: 8, mult: 2 },
  smrf: { slope: 0.2, window: 16, threshold: 0.45, scalar: 1.2, cut_smrf: false, elm: true, outlier: true },
  smoothing: { enabled: true, sigma: 1.0, order: 0, window: 3 },
  derivatives: {
    slopes: true, slopes_res: 1,
    aspect: true, aspect_res: 1,
    tpi: true, tpi_radii: [270, 810, 2430],
    interpolation: false, inter_amp: 1,
  },
  heights: { enabled: false, source: 'las', step: 10 },
  vectors: { horizontals: [0.5, 2, 5, 10], tin: false },
  target_crs: 'EPSG:32637',
  deterministic: true, seed: 42,
}

export const defaultForestParams: ForestParams = {
  cmd: { enabled: true, threshold_surface: 0.5, threshold_shrub: 5, channels: { chm: true, its: true, den: true }, median_window: 3 },
  detection: { method: 'yolov5', sample_size: 400, bound: 24, season: 'summer' },
  stats: { enabled: true, percentiles: [50, 55, 60, 65, 70, 75, 80, 85, 90, 95], vci_step: 1, metrics: ['entropy', 'max', 'mean', 'std', 'skew', 'kurtosis', 'vci', 'area', 'percentiles'] },
  logging_category: { enabled: true, algorithm: 'threshold', features: ['dist', 'diam', 'hght'], thresholds: { hght: 5, dist_far: 10, dist_near: 4, diam: 16 } },
  extras: { fire: false, fire_res: 1, fire_sm: 1, wind: false, wind_res: 1, wind_sm: 1, tlo: true, peaks: false, peak_size: 3 },
}

export const defaultWaterParams: WaterParams = {
  segment: { threshold: 0.6, sample_size: 1024, bound: 0, smooth: 1, resolution: 0.5 },
  swamp: { segment: false, threshold: 0.5, smooth: 1, resolution: 0.5, classify: false },
  buffers: { coastal_m: 20, protective_m: 50, water_protection_m: 200 },
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
  restartTile: (jobId: string, tileId: string) => void
  restartFailedTiles: (jobId: string) => void
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
  scene: { id: 'scene-001', afs_dir: '/data/demo/afs', vls_dir: '/data/demo/vls', target_crs: 'EPSG:32637', reproject: true, deterministic: true, seed: 42 },
}

export const useProjectStore = create<ProjectStore>((set) => ({
  projects: [demoProject],
  assessment: {
    'demo-001': {
      afs: {
        crs: 'EPSG:32637', extent_area_km2: 1.0, resolution_m: 0.14, ofp_scale: '1:1400',
        tiles_total: 1, tiles_ok: 1, tiles_failed: 0, failed_tiles: [],
      },
      vls: {
        crs: 'EPSG:32637', extent_area_km2: 1.0, density_pts_m2: 4577, tlo_scale: '1:500',
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
  restartTile: (jobId, tileId) =>
    set((s) => ({
      jobs: s.jobs.map((j) => {
        if (j.id !== jobId) return j
        const tiles = j.tiles.map((t) =>
          t.id === tileId && (t.status === 'failed' || t.status === 'skipped') ? makeRetryTile(t, j.type) : t
        )
        const agg = recompute(tiles)
        const processed = agg.tiles_done + agg.tiles_failed + agg.tiles_skipped
        return {
          ...j, tiles, ...agg,
          progress: Math.round((processed / j.tiles_total) * 100),
          status: 'running',
          finished_at: undefined,
        }
      }),
    })),
  restartFailedTiles: (jobId) =>
    set((s) => ({
      jobs: s.jobs.map((j) => {
        if (j.id !== jobId) return j
        const tiles = j.tiles.map((t) => (t.status === 'failed' ? makeRetryTile(t, j.type) : t))
        const agg = recompute(tiles)
        const processed = agg.tiles_done + agg.tiles_failed + agg.tiles_skipped
        return {
          ...j, tiles, ...agg,
          progress: Math.round((processed / j.tiles_total) * 100),
          status: 'running',
          finished_at: undefined,
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
}))