import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultReliefParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, InfoHint } from '@/components/ui/controls'
import { ModuleHeader } from '@/components/ui/ModuleHeader'
import { METHOD_TOOLTIPS } from '@/lib/methodTooltips'
import { Play, AlertTriangle } from 'lucide-react'
import type { ReliefParams, Job, SmoothingPreset, FilterMethod } from '@/api/types'
import { checkDependencies } from '@/lib/dependencies'

const FILTER_METHOD_LABELS: Record<FilterMethod, string> = {
  smrf: 'SMRF',
  manual: 'Ручная',
  stat: 'Статистическая',
  range: 'Перцентильная',
  kmeans: 'Outlier',
}

export default function Relief() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useSettingsStore()
  const projects = useProjectStore((s) => s.projects)
  const addJob = useProjectStore((s) => s.addJob)
  const project = projects.find((p) => p.id === projectId)
  const [p, setP] = useState<ReliefParams>(() =>
    (location.state as { retryParams?: ReliefParams } | null)?.retryParams ?? defaultReliefParams
  )
  const set = <K extends keyof ReliefParams>(k: K, v: ReliefParams[K]) => setP((s) => ({ ...s, [k]: v }))

  // Маппинг предустановок сглаживания → sigma/expert-параметры
  const handleSmoothingPreset = (v: SmoothingPreset) => {
    set('smoothing_preset', v)
    const sigmaByPreset: Record<SmoothingPreset, number> = { none: 0, light: 0.5, medium: 1.0, strong: 2.0 }
    setP((s) => ({
      ...s,
      smoothing_preset: v,
      smoothing: { ...s.smoothing, enabled: v !== 'none', sigma: sigmaByPreset[v] },
    }))
  }

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      project_id: projectId, type: 'relief', status: 'queued', progress: 0,
      tiles_total: 24, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [], tiles: [],
      started_at: new Date().toISOString(),
      params: {
        ...p,
        // Целевая СК и детерминизм — из «Параметров проекта» (ранее дублировались в UI)
        target_crs: project?.scene.target_crs || settings.default_target_crs,
        deterministic: project?.scene.deterministic ?? settings.deterministic.enabled,
        seed: project?.scene.seed ?? settings.deterministic.seed,
      },
    }
    addJob(job)
    navigate(`/projects/${projectId}/tasks`)
  }

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  const deps = checkDependencies(projectId || '', 'relief')
  const runTooltip = deps.ok
    ? undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Рассчитайте на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1>Рельеф</h1>
          <p className="mt-1 text-sm text-slate-500">
            Параметры обработки
            {isRetry && <span className="ml-2 text-brand-600">· повтор с новыми параметрами (новая сессия)</span>}
          </p>
        </div>
        <Button onClick={handleRun} disabled={!deps.ok} title={runTooltip}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {!deps.ok && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          <span>Не хватает: {deps.missing.map((m) => `${m.layer} (вкладка «${m.tab}»)`).join(', ')}</span>
        </div>
      )}

      <ModuleHeader
        projectId={projectId || ''}
        smoothingPreset={p.smoothing_preset}
        resolutionPreset={p.output_resolution_preset}
        onSmoothingChange={handleSmoothingPreset}
        onResolutionChange={(v) => set('output_resolution_preset', v)}
      />

      {/* Классификация рельефа */}
      <Card>
        <CardPad>
          <Accordion title="Классификация «Рельеф»" badge={FILTER_METHOD_LABELS[p.filter_method]}>
            <div className="space-y-4">
              <div className="flex flex-wrap gap-5">
                <span className="inline-flex items-center gap-1.5">
                  <Radio checked={p.filter_method === 'smrf'} onChange={() => set('filter_method', 'smrf')} label="SMRF" />
                  <InfoHint text={METHOD_TOOLTIPS.smrf} />
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Radio checked={p.filter_method === 'manual'} onChange={() => set('filter_method', 'manual')} label="Ручная" />
                  <InfoHint text={METHOD_TOOLTIPS.manual} />
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Radio checked={p.filter_method === 'stat'} onChange={() => set('filter_method', 'stat')} label="Статистическая" />
                  <InfoHint text={METHOD_TOOLTIPS.stat} />
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Radio checked={p.filter_method === 'range'} onChange={() => set('filter_method', 'range')} label="Перцентильная" />
                  <InfoHint text={METHOD_TOOLTIPS.range} />
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Radio checked={p.filter_method === 'kmeans'} onChange={() => set('filter_method', 'kmeans')} label="Outlier" />
                  <InfoHint text={METHOD_TOOLTIPS.kmeans} />
                </span>
              </div>

              {p.filter_method === 'manual' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Z min"><NumberInput value={p.filter.spm_min || 0} onChange={(v) => set('filter', { ...p.filter, spm_min: v })} /></Field>
                  <Field label="Z max"><NumberInput value={p.filter.spm_max || 100} onChange={(v) => set('filter', { ...p.filter, spm_max: v })} /></Field>
                </div>
              )}
              {p.filter_method === 'stat' && (
                <Field label="Коэффициент m·σ"><NumberInput value={p.filter.mult || 2} step={0.1} onChange={(v) => set('filter', { ...p.filter, mult: v })} /></Field>
              )}
              {p.filter_method === 'range' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="min, %"><NumberInput value={p.filter.spp_min || 1} onChange={(v) => set('filter', { ...p.filter, spp_min: v })} /></Field>
                  <Field label="max, %"><NumberInput value={p.filter.spp_max || 99} onChange={(v) => set('filter', { ...p.filter, spp_max: v })} /></Field>
                </div>
              )}
              {p.filter_method === 'kmeans' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="mean_k"><NumberInput value={p.filter.mean_k || 8} onChange={(v) => set('filter', { ...p.filter, mean_k: v })} /></Field>
                  <Field label="multiplier"><NumberInput value={p.filter.mult || 2} step={0.1} onChange={(v) => set('filter', { ...p.filter, mult: v })} /></Field>
                </div>
              )}

              {p.filter_method === 'smrf' && (
                <div className="border-t border-slate-100 pt-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Параметры SMRF</span>
                    <InfoHint text="Simple Morphological Filter — алгоритм выделения точек рельефа. Параметры по умолчанию: slope=0.2, window=16, threshold=0.45, scalar=1.2." />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <Field label="slope"><NumberInput value={p.smrf.slope} step={0.05} onChange={(v) => set('smrf', { ...p.smrf, slope: v })} /></Field>
                    <Field label="window"><NumberInput value={p.smrf.window} onChange={(v) => set('smrf', { ...p.smrf, window: v })} /></Field>
                    <Field label="threshold"><NumberInput value={p.smrf.threshold} step={0.05} onChange={(v) => set('smrf', { ...p.smrf, threshold: v })} /></Field>
                    <Field label="scalar"><NumberInput value={p.smrf.scalar} step={0.1} onChange={(v) => set('smrf', { ...p.smrf, scalar: v })} /></Field>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4">
                    <Checkbox checked={p.smrf.elm} onChange={(v) => set('smrf', { ...p.smrf, elm: v })} label="ELM-фильтр" />
                    <Checkbox checked={p.smrf.outlier} onChange={(v) => set('smrf', { ...p.smrf, outlier: v })} label="Outlier-фильтр" />
                    <Checkbox checked={p.smrf.cut_smrf} onChange={(v) => set('smrf', { ...p.smrf, cut_smrf: v })} label="Доп. отсечение" />
                  </div>
                </div>
              )}
            </div>
          </Accordion>
        </CardPad>
      </Card>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Сглаживание */}
        <Card>
          <CardPad>
            <Accordion title="Сглаживание ЦМР">
              <div className="space-y-3">
                <Checkbox checked={p.smoothing.enabled} onChange={(v) => set('smoothing', { ...p.smoothing, enabled: v })} label="Включить сглаживание" />
                <div className={`grid grid-cols-3 gap-3 ${p.smoothing.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                  <Field label="sigma" tooltip="Коэффициент умножается на пространственное разрешение растра. Чем больше — тем сильнее сглаживание.">
                    <NumberInput value={p.smoothing.sigma} step={0.1} onChange={(v) => set('smoothing', { ...p.smoothing, sigma: v })} />
                  </Field>
                  <Field label="order"><NumberInput value={p.smoothing.order} onChange={(v) => set('smoothing', { ...p.smoothing, order: v })} /></Field>
                  <Field label="window"><NumberInput value={p.smoothing.window} onChange={(v) => set('smoothing', { ...p.smoothing, window: v })} /></Field>
                </div>
              </div>
            </Accordion>
          </CardPad>
        </Card>

        {/* Производные слои */}
        <Card>
          <CardPad>
            <Accordion title="Производные слои">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox checked={p.derivatives.slopes} onChange={(v) => set('derivatives', { ...p.derivatives, slopes: v })} label="Карта уклонов" />
                    <InfoHint text="Расчёт угла наклона поверхности в градусах от ЦМР. slopes_res — разрешение выходного растра уклонов в метрах." />
                  </span>
                  <NumberInput value={p.derivatives.slopes_res} step={0.1} onChange={(v) => set('derivatives', { ...p.derivatives, slopes_res: v })} disabled={!p.derivatives.slopes} className="w-28" />
                </div>
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox checked={p.derivatives.aspect} onChange={(v) => set('derivatives', { ...p.derivatives, aspect: v })} label="Карта экспозиций" />
                    <InfoHint text="Направление уклона поверхности (азимут, 0-360°). aspect_res — разрешение выходного растра экспозиций в метрах." />
                  </span>
                  <NumberInput value={p.derivatives.aspect_res} step={0.1} onChange={(v) => set('derivatives', { ...p.derivatives, aspect_res: v })} disabled={!p.derivatives.aspect} className="w-28" />
                </div>
                <div>
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox checked={p.derivatives.tpi} onChange={(v) => set('derivatives', { ...p.derivatives, tpi: v })} label="TPI (трёхмасштабный)" />
                    <InfoHint text="Topographic Position Index — отклонение высоты точки от среднего в окрестности. Три радиуса (мелкий/средний/крупный) для выявления форм рельефа разного масштаба." />
                  </span>
                  {p.derivatives.tpi && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                        Радиусы, м:
                        <InfoHint text="Три радиуса поиска в метрах: мелкий (детали), средний (формы), крупный (контекст)." />
                      </span>
                      {[0, 1, 2].map((i) => (
                        <NumberInput
                          key={i} className="w-20"
                          value={p.derivatives.tpi_radii[i] || 0}
                          onChange={(v) => {
                            const radii = [...p.derivatives.tpi_radii]; radii[i] = v
                            set('derivatives', { ...p.derivatives, tpi_radii: radii })
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox checked={p.derivatives.interpolation} onChange={(v) => set('derivatives', { ...p.derivatives, interpolation: v })} label="Интерполяция (IDW)" />
                    <InfoHint text="Inverse Distance Weighting — интерполяция ЦМР обратно взвешенным расстоянием. inter_amp — амплитуда сглаживания." />
                  </span>
                  <NumberInput value={p.derivatives.inter_amp} step={0.1} onChange={(v) => set('derivatives', { ...p.derivatives, inter_amp: v })} disabled={!p.derivatives.interpolation} className="w-28" />
                </div>
              </div>
            </Accordion>
          </CardPad>
        </Card>
      </div>

      {/* Высоты + TIN */}
      <Card>
        <CardPad>
          <Accordion title="Высоты и TIN">
            <div className="space-y-5">
              <div>
                <Checkbox checked={p.heights.enabled} onChange={(v) => set('heights', { ...p.heights, enabled: v })} label="Извлечь высоты" />
                <div className={`mt-2 space-y-3 ${p.heights.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                  <div className="flex gap-5">
                    <Radio checked={p.heights.source === 'las'} onChange={() => set('heights', { ...p.heights, source: 'las' })} label="Из LAS-точек" />
                    <Radio checked={p.heights.source === 'dem'} onChange={() => set('heights', { ...p.heights, source: 'dem' })} label="Из растра ЦМР" />
                  </div>
                  <Field label="Шаг точек (каждая n-я)"><NumberInput value={p.heights.step} onChange={(v) => set('heights', { ...p.heights, step: v })} className="w-28" /></Field>
                </div>
              </div>
              <div className="border-t border-slate-100 pt-3">
                <Checkbox checked={p.vectors.tin} onChange={(v) => set('vectors', { ...p.vectors, tin: v })} label="TIN (DXF)" />
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      <Card>
        <CardPad>
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Целевая СК и детерминизм наследуются из «Параметров проекта»</span>
            <span className="font-mono">{project?.scene.target_crs || settings.default_target_crs} · seed {project?.scene.seed ?? settings.deterministic.seed}</span>
          </div>
        </CardPad>
      </Card>
    </div>
  )
}