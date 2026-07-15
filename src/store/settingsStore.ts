import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { GlobalSettings } from '@/api/types'

const defaultSettings: GlobalSettings = {
  model_paths: {
    treecanopy: '',
    water: '',
    swamp: '',
    forest: '',
  },
  data_dir: '',
  results_dir: '',
  default_season: 'summer',
  default_satellite: 'aerial',
  default_target_crs: '',
  deterministic: {
    enabled: true,
    seed: 42,
    cudnn_deterministic: true,
    cudnn_benchmark: false,
    num_workers: 0,
  },
}

interface SettingsStore {
  settings: GlobalSettings
  update: (patch: Partial<GlobalSettings>) => void
  updateDeterministic: (patch: Partial<GlobalSettings['deterministic']>) => void
  updateModelPaths: (patch: Partial<GlobalSettings['model_paths']>) => void
  reset: () => void
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      settings: defaultSettings,
      update: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
      updateDeterministic: (patch) =>
        set((s) => ({ settings: { ...s.settings, deterministic: { ...s.settings.deterministic, ...patch } } })),
      updateModelPaths: (patch) =>
        set((s) => ({ settings: { ...s.settings, model_paths: { ...s.settings.model_paths, ...patch } } })),
      reset: () => set({ settings: defaultSettings }),
    }),
    { name: 'sima-settings' },
  ),
)