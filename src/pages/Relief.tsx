import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultReliefParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, InfoHint, Select } from '@/components/ui/controls'
import { ModuleHeader, SIGMA_BY_PRESET } from '@/components/ui/ModuleHeader'
import { METHOD_TOOLTIPS } from '@/lib/methodTooltips'
import { Play, AlertTriangle } from 'lucide-react'
import type { ReliefParams, Job, SmoothingPreset, FilterMethod } from '@/api/types'
import { checkDependencies } from '@/lib/dependencies'

const FILTER_METHOD_LABELS: Record<FilterMethod, string> = {
  smrf: 'SMRF',
  las_class: 'Из классификации LAS',
  manual: 'Ручная',
  stat: 'Статистическая',
  range: 'Перцентильная',
  kmeans: 'Outlier',
}

// Повтор ранее посчитанной сессии: её параметры могли быть сохранены до
// изменения контракта, поэтому недостающие поля добираем из умолчаний.
function withDefaults(rp?: ReliefParams): ReliefParams {
  if (!rp) return defaultReliefParams
  const d = defaultReliefParams
  return {
    ...d, ...rp,
    filter: { ...d.filter, ...rp.filter },
    smrf: { ...d.smrf, ...rp.smrf },
    smoothing: { ...d.smoothing, ...rp.smoothing },
    dsm: { ...d.dsm, ...rp.dsm },
    derivatives: { ...d.derivatives, ...rp.derivatives },
    heights: { ...d.heights, ...rp.heights },
    vectors: { ...d.vectors, ...rp.vectors },
  }
}

// Один слой в блоке «Интерполяция и экстраполяция». Параметры задаются
// независимо для ЦМР, карты уклонов и карты экспозиций.
function InterpolationBlock({ title, hint, enabled, amp, edge, disabled, disabledHint, onChange }: {
  title: string
  hint: string
  enabled: boolean
  amp: number
  edge: number
  disabled?: boolean
  disabledHint?: string
  onChange: (patch: { enabled?: boolean; amp?: number; edge?: number }) => void
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <span className="inline-flex items-center gap-1.5">
        <Checkbox checked={enabled} onChange={(v) => onChange({ enabled: v })} label={title} disabled={disabled} />
        <InfoHint text={hint} />
      </span>
      {disabled ? (
        <p className="hint-base mt-2">{disabledHint}</p>
      ) : (
        <div className={`mt-2 space-y-3 ${enabled ? '' : 'opacity-40 pointer-events-none'}`}>
          <Field label="Амплитуда интерполяции" tooltip="inter_amp — радиус поиска значений при заполнении пустот обратно взвешенным расстоянием (IDW).">
            <NumberInput value={amp} step={0.1} min={0} onChange={(v) => onChange({ amp: v })} />
          </Field>
          <Field label="Экстраполяция края, м" tooltip="На сколько метров допустимо выйти за границу валидной области. 0 — заполнять только внутренние дыры: пустоты, касающиеся рамки растра, остаются незаполненными.">
            <NumberInput value={edge} step={1} min={0} onChange={(v) => onChange({ edge: v })} />
          </Field>
        </div>
      )}
    </div>
  )
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
    withDefaults((location.state as { retryParams?: ReliefParams } | null)?.retryParams)
  )
  const set = <K extends keyof ReliefParams>(k: K, v: ReliefParams[K]) => setP((s) => ({ ...s, [k]: v }))

  // Маппинг предустановок сглаживания → sigma/expert-параметры. В режиме
  // «Пользовательское» sigma не подменяется — её задаёт пользователь.
  const handleSmoothingPreset = (v: SmoothingPreset) => {
    setP((s) => ({
      ...s,
      smoothing_preset: v,
      smoothing: {
        ...s.smoothing,
        enabled: true,
        sigma: v === 'custom' ? s.smoothing.sigma : SIGMA_BY_PRESET[v],
      },
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
        customSmoothing={{ sigma: p.smoothing.sigma, order: p.smoothing.order, window: p.smoothing.window }}
        onCustomSmoothingChange={(patch) => setP((s) => ({ ...s, smoothing: { ...s.smoothing, ...patch } }))}
        customResolutionM={p.output_resolution_m}
        onCustomResolutionChange={(v) => set('output_resolution_m', v)}
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
                  <Radio checked={p.filter_method === 'las_class'} onChange={() => set('filter_method', 'las_class')} label="Из классификации LAS" />
                  <InfoHint text={METHOD_TOOLTIPS.las_class} />
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

              {p.filter_method === 'las_class' && (
                <p className="hint-base">
                  Земля берётся из классификации входного LAS (класс 2 по ASPRS). Собственная
                  классификация не выполняется. Если в файле класса 2 нет, тайл отработает по SMRF.
                </p>
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
        {/* ЦММ — второй основной выход модуля, вход «Древостоя» */}
        <Card>
          <CardPad>
            <Accordion title="Цифровая модель местности" badge="ЦММ">
              <div className="space-y-3">
                <Checkbox
                  checked={p.dsm.enabled}
                  onChange={(v) => set('dsm', { ...p.dsm, enabled: v })}
                  label="Строить ЦММ"
                />
                <p className="hint-base">
                  ЦММ (поверхность вместе с объектами) — вход модуля «Древостой». Без неё сессия не появится
                  в списке источников ЦММ.
                </p>
                <div className={`space-y-3 ${p.dsm.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Агрегация точек" tooltip="Как высота точек сводится в пиксель растра: max — верхняя точка (легаси CMD.py), mean — среднее, idw — обратно взвешенное расстояние.">
                      <Select
                        value={p.dsm.output_type}
                        onChange={(e) => set('dsm', { ...p.dsm, output_type: e.target.value as ReliefParams['dsm']['output_type'] })}
                      >
                        <option value="max">max (верхняя точка)</option>
                        <option value="mean">mean (среднее)</option>
                        <option value="idw">idw (взвешенное)</option>
                      </Select>
                    </Field>
                    <Field label="Радиус поиска, пикс" tooltip="max_search_distance — радиус заполнения пустот при интерполяции ЦММ.">
                      <NumberInput
                        value={p.dsm.max_search_distance}
                        min={0}
                        onChange={(v) => set('dsm', { ...p.dsm, max_search_distance: v })}
                      />
                    </Field>
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <Checkbox checked={p.dsm.interpolate} onChange={(v) => set('dsm', { ...p.dsm, interpolate: v })} label="Интерполяция" />
                    <Checkbox checked={p.dsm.fill_holes} onChange={(v) => set('dsm', { ...p.dsm, fill_holes: v })} label="Заполнять пустоты" />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="text-sm">Экстраполяция края, м</span>
                      <InfoHint text="На сколько метров допустимо продлить ЦММ за границу валидной области. 0 — заполнять только внутренние дыры." />
                    </span>
                    <NumberInput
                      value={p.dsm.edge_extrapolation_m}
                      step={1}
                      min={0}
                      onChange={(v) => set('dsm', { ...p.dsm, edge_extrapolation_m: v })}
                      className="w-28"
                    />
                  </div>
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
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5">
                      <Checkbox checked={p.derivatives.tpi} onChange={(v) => set('derivatives', { ...p.derivatives, tpi: v })} label="TPI (трёхмасштабный)" />
                      <InfoHint text="Topographic Position Index — отклонение высоты точки от среднего в окрестности. Три радиуса (мелкий/средний/крупный) для выявления форм рельефа разного масштаба. Правое поле — пространственное разрешение выходного растра TPI в метрах." />
                    </span>
                    <NumberInput value={p.derivatives.tpi_res} step={0.1} min={0.01} onChange={(v) => set('derivatives', { ...p.derivatives, tpi_res: v })} disabled={!p.derivatives.tpi} className="w-28" />
                  </div>
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
                <p className="hint-base">
                  Интерполяция и экстраполяция вынесены в отдельный блок ниже.
                </p>
              </div>
            </Accordion>
          </CardPad>
        </Card>
      </div>

      {/* Интерполяция и экстраполяция — раздельно по выходам */}
      <Card>
        <CardPad>
          <Accordion title="Интерполяция и экстраполяция">
            <div className="grid gap-3 md:grid-cols-3">
              <InterpolationBlock
                title="ЦМР"
                hint="Заполнение пустот ЦМР перед расчётом производных. Выполняется до сглаживания и построения уклонов/экспозиций."
                enabled={p.derivatives.interpolation}
                amp={p.derivatives.inter_amp}
                edge={p.derivatives.edge_extrapolation_m}
                onChange={(patch) => set('derivatives', {
                  ...p.derivatives,
                  ...(patch.enabled !== undefined && { interpolation: patch.enabled }),
                  ...(patch.amp !== undefined && { inter_amp: patch.amp }),
                  ...(patch.edge !== undefined && { edge_extrapolation_m: patch.edge }),
                })}
              />
              <InterpolationBlock
                title="Карта уклонов"
                hint="Заполнение пустот карты уклонов. Задаётся независимо от ЦМР."
                enabled={p.derivatives.slopes_interpolation}
                amp={p.derivatives.slopes_inter_amp}
                edge={p.derivatives.slopes_edge_extrapolation_m}
                disabled={!p.derivatives.slopes}
                disabledHint="Карта уклонов выключена в блоке «Производные слои»"
                onChange={(patch) => set('derivatives', {
                  ...p.derivatives,
                  ...(patch.enabled !== undefined && { slopes_interpolation: patch.enabled }),
                  ...(patch.amp !== undefined && { slopes_inter_amp: patch.amp }),
                  ...(patch.edge !== undefined && { slopes_edge_extrapolation_m: patch.edge }),
                })}
              />
              <InterpolationBlock
                title="Карта экспозиций"
                hint="Заполнение пустот карты экспозиций. Задаётся независимо от ЦМР."
                enabled={p.derivatives.aspect_interpolation}
                amp={p.derivatives.aspect_inter_amp}
                edge={p.derivatives.aspect_edge_extrapolation_m}
                disabled={!p.derivatives.aspect}
                disabledHint="Карта экспозиций выключена в блоке «Производные слои»"
                onChange={(patch) => set('derivatives', {
                  ...p.derivatives,
                  ...(patch.enabled !== undefined && { aspect_interpolation: patch.enabled }),
                  ...(patch.amp !== undefined && { aspect_inter_amp: patch.amp }),
                  ...(patch.edge !== undefined && { aspect_edge_extrapolation_m: patch.edge }),
                })}
              />
            </div>
          </Accordion>
        </CardPad>
      </Card>

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
                  <Field
                    label="Минимальное расстояние между точками, м"
                    tooltip="Пространственное прореживание отметок: точки ближе указанного расстояния отбрасываются."
                  >
                    <NumberInput value={p.heights.min_distance_m} step={0.1} min={0} onChange={(v) => set('heights', { ...p.heights, min_distance_m: v })} className="w-28" />
                  </Field>
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