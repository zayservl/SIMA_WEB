import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultForestParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, Input, InfoHint, Select } from '@/components/ui/controls'
import { ModuleHeader, SIGMA_BY_PRESET } from '@/components/ui/ModuleHeader'
import { RunSetup } from '@/components/ui/RunSetup'
import { Play, AlertTriangle } from 'lucide-react'
import type { ForestParams, Job, ReliefParams, SmoothingPreset, ResolutionPreset, ParamMode, VoidFillMethod } from '@/api/types'
import { defaultJobName } from '@/lib/jobs'
import { checkDependencies, hasAfs } from '@/lib/dependencies'

// Выбор способа определения параметров блока. В режиме «ИИ» ручные параметры
// блока не задаются — их подбирает модель, поля гасятся вызывающим кодом.
// «Категория рубки» переключателя не имеет: она считается только алгоритмически.
function ParamModeSwitch({ mode, onChange, aiLabel = 'ИИ', algorithmicLabel = 'Алгоритмически', aiHint }: {
  mode: ParamMode
  onChange: (v: ParamMode) => void
  aiLabel?: string
  algorithmicLabel?: string
  aiHint?: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
        <span className="label-base">Определение параметров</span>
        <Radio checked={mode === 'ai'} onChange={() => onChange('ai')} label={aiLabel} />
        <Radio checked={mode === 'algorithmic'} onChange={() => onChange('algorithmic')} label={algorithmicLabel} />
      </div>
      {mode === 'ai' && aiHint && <p className="hint-base mt-1">{aiHint}</p>}
    </div>
  )
}

// Повтор ранее посчитанной сессии: её параметры могли быть сохранены до
// изменения контракта, поэтому недостающие поля добираем из умолчаний.
function withDefaults(fp?: ForestParams): ForestParams {
  if (!fp) return defaultForestParams
  const d = defaultForestParams
  return {
    ...d, ...fp,
    cmd: { ...d.cmd, ...fp.cmd, channels: { ...d.cmd.channels, ...fp.cmd?.channels }, fill: { ...d.cmd.fill, ...fp.cmd?.fill } },
    detection: {
      ...d.detection, ...fp.detection,
      afs_correction: { ...d.detection.afs_correction, ...fp.detection?.afs_correction },
      cost_weights: { ...d.detection.cost_weights, ...fp.detection?.cost_weights },
    },
    stats: { ...d.stats, ...fp.stats },
    smoothing: { ...d.smoothing, ...fp.smoothing },
    logging_category: { ...d.logging_category, ...fp.logging_category },
  }
}

export default function Forest() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useSettingsStore()
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
  const [p, setP] = useState<ForestParams>(() =>
    withDefaults((location.state as { retryParams?: ForestParams } | null)?.retryParams)
  )
  const [jobName, setJobName] = useState(() => defaultJobName('forest', jobs, projectId ?? ''))
  const set = <K extends keyof ForestParams>(k: K, v: ForestParams[K]) => setP((s) => ({ ...s, [k]: v }))

  // Пресет сглаживания задаёт sigma; в режиме «Пользовательское» её вводят руками.
  const handleSmoothingPreset = (v: SmoothingPreset) =>
    setP((s) => ({
      ...s,
      smoothing_preset: v,
      smoothing: {
        ...s.smoothing,
        enabled: true,
        sigma: v === 'custom' ? s.smoothing.sigma : SIGMA_BY_PRESET[v],
      },
    }))

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      name: jobName.trim() || defaultJobName('forest', jobs, projectId),
      project_id: projectId, type: 'forest', status: 'queued', progress: 0,
      tiles_total: 18, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [], tiles: [],
      started_at: new Date().toISOString(),
      params: {
        ...p,
        // Без АФС детекция крон и зависящие от неё статистики не выполняются.
        detection: { ...p.detection, enabled: detectionEnabled },
        stats: { ...p.stats, enabled: p.stats.enabled && detectionEnabled },
      },
    }
    addJob(job)
    navigate(`/projects/${projectId}/tasks`)
  }

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  const deps = checkDependencies(projectId || '', 'forest', { dsm_source: p.dsm_source })
  const runTooltip = deps.ok
    ? undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Рассчитайте на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

  // Завершённые задачи рельефа в рамках текущего проекта.
  const reliefJobs = projectId
    ? jobs.filter((j) => j.project_id === projectId && j.type === 'relief' && j.status === 'success')
    : []

  // Источник ЦММ — только сессии, где ЦММ действительно строилась: сервис
  // рельефа выполняет шаг ЦММ лишь при dsm.enabled, иначе растра в сессии нет.
  const dsmJobs = reliefJobs.filter((j) => (j.params as ReliefParams).dsm?.enabled)

  // Отдельного выбора производных рельефа нет: они подставляются из той же
  // сессии, что и ЦММ. Держим derivatives_source синхронным с dsm_source.
  const setDsmSession = (sessionId: string | undefined) =>
    setP((s) => ({
      ...s,
      dsm_source: { ...s.dsm_source, system_session_id: sessionId },
      derivatives_source: { ...s.derivatives_source, kind: s.dsm_source.kind, system_session_id: sessionId },
    }))

  // Какие производные реально посчитаны в выбранной сессии — показываем, чтобы
  // выбор ЦММ не тянул за собой молчаливо пустой набор производных.
  const selectedJob = dsmJobs.find((j) => (j.session_id ?? j.id) === p.dsm_source.system_session_id)
  const selectedDerivatives = selectedJob
    ? (() => {
        const d = (selectedJob.params as ReliefParams).derivatives
        return [
          d?.slopes && 'уклоны',
          d?.aspect && 'экспозиции',
          d?.tpi && 'TPI',
        ].filter(Boolean) as string[]
      })()
    : null

  // Детекция крон идёт по ортофотоплану: без АФС расчёт недоступен.
  const afsAvailable = hasAfs(projectId || '')
  const detectionEnabled = p.detection.enabled && afsAvailable

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1>Древостой</h1>
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

      <RunSetup name={jobName} onNameChange={setJobName} />

      {/* Шапка модуля: СК, сглаживание, разрешение + переключатели источника */}
      <ModuleHeader
        projectId={projectId ?? ''}
        smoothingPreset={p.smoothing_preset}
        resolutionPreset={p.output_resolution_preset}
        onSmoothingChange={handleSmoothingPreset}
        onResolutionChange={(v: ResolutionPreset) => set('output_resolution_preset', v)}
        customSmoothing={p.smoothing}
        onCustomSmoothingChange={(patch) => setP((s) => ({ ...s, smoothing: { ...s.smoothing, ...patch } }))}
      >
        {/* Источник ЦММ — только рассчитанная в системе сессия «Рельефа».
            Производные рельефа берутся из неё же, отдельного выбора нет. */}
        <div className="rounded-lg border border-slate-200 p-3 sm:max-w-md">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Источник ЦММ</div>
          <Select
            value={p.dsm_source.system_session_id ?? ''}
            onChange={(e) => setDsmSession(e.target.value || undefined)}
          >
            <option value="">— выбрать сессию —</option>
            {dsmJobs.map((j) => (
              <option key={j.id} value={j.session_id ?? j.id}>
                {j.session_id ?? j.id}
              </option>
            ))}
          </Select>
          {dsmJobs.length === 0 ? (
            <p className="hint-base mt-1.5">Нет сессий «Рельефа» с построенной ЦММ</p>
          ) : selectedDerivatives ? (
            <p className="hint-base mt-1.5">
              Производные рельефа подставляются из этой же сессии:{' '}
              {selectedDerivatives.length ? selectedDerivatives.join(', ') : 'в сессии не рассчитаны'}
            </p>
          ) : (
            <p className="hint-base mt-1.5">Производные рельефа подставляются из выбранной сессии автоматически</p>
          )}
        </div>
      </ModuleHeader>

      {/* ЦМД */}
      <Card>
        <CardPad>
          <Accordion title="Цифровая модель древостоя" badge="ЦМД">
            <div className="space-y-4">
              <Checkbox checked={p.cmd.enabled} onChange={(v) => set('cmd', { ...p.cmd, enabled: v })} label="Формировать ЦМД" />
              <div className={`space-y-4 ${p.cmd.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <ParamModeSwitch
                  mode={p.cmd.mode}
                  onChange={(mode) => set('cmd', { ...p.cmd, mode })}
                  aiHint="Пороги ярусов и окно фильтра подбирает модель"
                />
                <div className={`space-y-4 ${p.cmd.mode === 'algorithmic' ? '' : 'opacity-40 pointer-events-none'}`}>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Field label="Поверхность (м)" tooltip="Высота точек, относимая к поверхности (класс 3). Точки ниже этого порога считаются поверхностью земли.">
                      <NumberInput value={p.cmd.threshold_surface} step={0.1} min={0} onChange={(v) => set('cmd', { ...p.cmd, threshold_surface: v })} />
                    </Field>
                    <Field label="Кустарники (м)" tooltip="Верхняя граница кустарникового яруса (класс 4). Выше — древесный ярус (класс 5).">
                      <NumberInput value={p.cmd.threshold_shrub} step={0.5} min={0} onChange={(v) => set('cmd', { ...p.cmd, threshold_shrub: v })} />
                    </Field>
                    <Field label="Медианный фильтр">
                      <NumberInput value={p.cmd.median_window} min={0} onChange={(v) => set('cmd', { ...p.cmd, median_window: v })} />
                    </Field>
                  </div>
                </div>
                <div>
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Каналы растра</span>
                    <InfoHint text="Дополнительные растры того же покрытия, что и ЦМД: интенсивность отражения (its.tif) и плотность точек (den.tif). Оба — вход поверхности стоимости при сегментации крон." />
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <Checkbox checked={p.cmd.channels.chm} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, chm: v } })} label="CHM (высота крон)" />
                    <Checkbox checked={p.cmd.channels.intensity} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, intensity: v } })} label="Интенсивность (ITS)" />
                    <Checkbox checked={p.cmd.channels.density} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, density: v } })} label="Плотность точек (DEN)" />
                    <Checkbox checked={p.cmd.save_classified_las} onChange={(v) => set('cmd', { ...p.cmd, save_classified_las: v })} label="Сохранять классифицированное облако" />
                  </div>
                </div>

                {/* Заполнение пустот полога */}
                <div className="rounded-lg border border-slate-200 p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Заполнение пустот полога</span>
                    <InfoHint text="Гидровыравнивание к ЦМД не применяется: на растре высот над землёй вода и так близка к нулю." />
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <Checkbox checked={p.cmd.fill.interpolate} onChange={(v) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, interpolate: v } })} label="Интерполяция" />
                    <Checkbox checked={p.cmd.fill.fill_holes} onChange={(v) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, fill_holes: v } })} label="Заполнять пустоты" />
                  </div>
                  <div className={`mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 ${p.cmd.fill.interpolate && p.cmd.fill.fill_holes ? '' : 'opacity-40 pointer-events-none'}`}>
                    <Field label="Метод" tooltip="laplace — гладкое решение уравнения Лапласа в пустоте; idw — GDALFillNodata, быстрее, но с радиальными лучами внутрь крупных пустот.">
                      <Select
                        value={p.cmd.fill.fill_method}
                        onChange={(e) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, fill_method: e.target.value as VoidFillMethod } })}
                      >
                        <option value="laplace">laplace</option>
                        <option value="idw">idw</option>
                      </Select>
                    </Field>
                    <Field label="Проходов">
                      <NumberInput value={p.cmd.fill.fill_passes} min={1} onChange={(v) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, fill_passes: v } })} />
                    </Field>
                    <Field label="Радиус поиска, пикс">
                      <NumberInput value={p.cmd.fill.max_search_distance} min={0} onChange={(v) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, max_search_distance: v } })} />
                    </Field>
                    <Field label="Экстраполяция края, м" tooltip="0 — заполнять только внутренние просветы полога, не выходя за границу данных.">
                      <NumberInput value={p.cmd.fill.edge_extrapolation_m} step={0.5} min={0} onChange={(v) => set('cmd', { ...p.cmd, fill: { ...p.cmd.fill, edge_extrapolation_m: v } })} />
                    </Field>
                  </div>
                </div>
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Детекция крон */}
      <Card>
        <CardPad>
          <Accordion title="Детекция крон">
            <div className="space-y-4">
              <Checkbox
                checked={p.detection.enabled}
                onChange={(v) => set('detection', { ...p.detection, enabled: v })}
                label="Выполнять детекцию крон"
                disabled={!afsAvailable}
              />
              {!afsAvailable && (
                <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <div>
                    АФС не загружены. Детекция крон идёт по ортофотоплану, поэтому расчёт недоступен —
                    остальные блоки модуля считаются по ВЛС и ЦММ.
                  </div>
                </div>
              )}
              <div className={`space-y-4 ${detectionEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <ParamModeSwitch
                  mode={p.detection.mode}
                  onChange={(mode) => set('detection', { ...p.detection, mode })}
                  aiLabel="ИИ (нейросеть YOLOv5)"
                  algorithmicLabel="Алгоритмически (водораздел)"
                  aiHint="Границы сегментов крон определяет модель"
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Состояние вегетации">
                    <Select
                      value={p.detection.vegetation_state}
                      onChange={(e) => set('detection', { ...p.detection, vegetation_state: e.target.value as 'active' | 'absent' })}
                    >
                      <option value="active">Активная</option>
                      <option value="absent">Отсутствует</option>
                    </Select>
                  </Field>
                  <Field label="Окно поиска вершин крон (м)" tooltip="Минимальное расстояние между соседними деревьями. Прямо определяет число найденных деревьев: чем шире окно, тем меньше вершин. Значение округляется до целого числа ячеек, поэтому фактическое окно зависит от разрешения ЦМД — при 1 м это 2.5 м на сетке 0.5 м и 3 м на сетке 1 м.">
                    <NumberInput
                      value={p.detection.peak_size_m}
                      step={0.5}
                      min={0}
                      onChange={(v) => set('detection', { ...p.detection, peak_size_m: v })}
                    />
                  </Field>
                </div>
                {/* Отсечки высоты и сглаживание ЦМД перед поиском максимумов */}
                <div className="rounded-lg border border-slate-200 p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Отсечки высоты</span>
                    <InfoHint text="Ячейки ЦМД вне диапазона обнуляются до поиска вершин: ниже нижней отсечки — не дерево, выше верхней — шум растра." />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Field label="Минимальная высота, м">
                      <NumberInput value={p.detection.min_height_m} step={0.1} min={0} onChange={(v) => set('detection', { ...p.detection, min_height_m: v })} />
                    </Field>
                    <Field label="Максимальная высота, м">
                      <NumberInput value={p.detection.max_height_m} step={1} min={0} onChange={(v) => set('detection', { ...p.detection, max_height_m: v })} />
                    </Field>
                    <Field label="Сглаживание, пикс" tooltip="Радиус медианного ядра, которым ЦМД сглаживается перед поиском максимумов. 0 — без сглаживания. Высота дерева при этом снимается с несглаженного растра: медианный фильтр срезает макушки.">
                      <NumberInput value={p.detection.smooth_radius_px} min={0} onChange={(v) => set('detection', { ...p.detection, smooth_radius_px: v })} />
                    </Field>
                  </div>
                </div>

                {/* Корректировка вершин по АФС */}
                <div className="rounded-lg border border-slate-200 p-3">
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox
                      checked={p.detection.afs_correction.enabled}
                      onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, enabled: v } })}
                      label="Корректировка вершин по снимку"
                    />
                    <InfoHint text="ЦМД не отличает дерево от столба или бровки отвала. Снимок различает их по цвету: вершина вне маски растительности отбрасывается, положение вершины уточняется по центру области кроны. Съёмка в видимом диапазоне, канала ближнего ИК нет — поэтому индексы по RGB, а не NDVI." />
                  </span>
                  <div className={`mt-3 space-y-3 ${p.detection.afs_correction.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <Field label="Индекс" tooltip="ExG = 2g − r − b по нормированным каналам — устойчив к яркости. VARI сильнее реагирует на слабую зелень, но шумит на тенях и пересветах.">
                        <Select
                          value={p.detection.afs_correction.index}
                          onChange={(e) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, index: e.target.value as 'exg' | 'vari' } })}
                        >
                          <option value="exg">ExG</option>
                          <option value="vari">VARI</option>
                        </Select>
                      </Field>
                      <Field label="Порог индекса">
                        <NumberInput value={p.detection.afs_correction.threshold} step={0.01} onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, threshold: v } })} />
                      </Field>
                      <Field label="Мин. пятно, пикс" tooltip="Связные области растительности мельче этой площади выбрасываются из маски. 0 — не отсеивать.">
                        <NumberInput value={p.detection.afs_correction.min_area_px} min={0} onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, min_area_px: v } })} />
                      </Field>
                      <Field label="Радиус уточнения, м" tooltip="Максимальный сдвиг вершины к центру области кроны. Дальний сдвиг означает слитный полог, а не отдельную крону — там исходное положение по ЦМД надёжнее.">
                        <NumberInput value={p.detection.afs_correction.refine_radius_m} step={0.5} min={0} onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, refine_radius_m: v } })} />
                      </Field>
                    </div>
                    <div className="flex flex-wrap gap-4">
                      <Checkbox checked={p.detection.afs_correction.drop_non_vegetation} onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, drop_non_vegetation: v } })} label="Отсеивать вершины вне растительности" />
                      <Checkbox checked={p.detection.afs_correction.refine_position} onChange={(v) => set('detection', { ...p.detection, afs_correction: { ...p.detection.afs_correction, refine_position: v } })} label="Уточнять положение вершин" />
                    </div>
                  </div>
                </div>

                {/* Поверхность стоимости водораздела */}
                <div className="rounded-lg border border-slate-200 p-3">
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Границы крон: веса признаков</span>
                    <InfoHint text="По каким признакам водораздел проводит границу между соседними кронами. Число крон от весов не зависит — оно равно числу вершин; веса меняют только положение границ. Все веса, кроме «высоты», равные нулю — заливка только по высоте полога." />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {([
                      ['height', 'Высота полога'],
                      ['chm_gradient', 'Перепад ЦМД'],
                      ['afs_edges', 'Границы снимка'],
                      ['afs_texture', 'Текстура снимка'],
                      ['intensity', 'Интенсивность'],
                      ['density', 'Плотность точек'],
                    ] as const).map(([key, label]) => (
                      <Field key={key} label={label}>
                        <NumberInput
                          value={p.detection.cost_weights[key]}
                          step={0.1}
                          min={0}
                          onChange={(v) => set('detection', { ...p.detection, cost_weights: { ...p.detection.cost_weights, [key]: v } })}
                        />
                      </Field>
                    ))}
                    <Field label="Окно текстуры, пикс" tooltip="Размер окна локального СКО, которым считаются текстурные границы снимка.">
                      <NumberInput value={p.detection.cost_weights.texture_window} min={1} onChange={(v) => set('detection', { ...p.detection, cost_weights: { ...p.detection.cost_weights, texture_window: v } })} />
                    </Field>
                  </div>
                </div>

                {p.detection.mode === 'ai' && (
                  <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                    Каталог весов: <code className="text-slate-700">{settings.model_paths.treecanopy || 'не задан'}</code>
                  </div>
                )}
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Статистики ТЛО */}
      <Card>
        <CardPad>
          <Accordion title="Статистики по сегментам крон" defaultOpen={false}>
            <div className="space-y-4">
              <Checkbox
                checked={p.stats.enabled}
                onChange={(v) => set('stats', { ...p.stats, enabled: v })}
                label="Собрать статистики"
                disabled={!detectionEnabled}
              />
              {!detectionEnabled && (
                <p className="hint-base">Статистики считаются по сегментам крон — требуется детекция крон</p>
              )}
              <div className={`space-y-4 ${p.stats.enabled && detectionEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <div className="flex items-center gap-2">
                  <Field label="Перцентили (через запятую)" tooltip="Перцентили распределения высот точек внутри каждого сегмента кроны. Используются для оценки структуры древостоя." className="flex-1">
                    <Input
                      value={p.stats.percentiles.join(', ')}
                      onChange={(e) => set('stats', { ...p.stats, percentiles: e.target.value.split(',').map((x) => parseInt(x.trim())).filter((x) => !isNaN(x)) })}
                    />
                  </Field>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <span className="label-base">Шаг VCI, м</span>
                    <div className="mt-1.5 flex gap-5">
                      <Radio checked={p.stats.vci_step === 1} onChange={() => set('stats', { ...p.stats, vci_step: 1 })} label="1.0" />
                      <Radio checked={p.stats.vci_step === 0.5} onChange={() => set('stats', { ...p.stats, vci_step: 0.5 })} label="0.5" />
                    </div>
                  </div>
                  <Field
                    label="Отсечка при устойчивой высоте"
                    tooltip="Доля самых высоких ячеек кроны, отбрасываемых при расчёте height_robust_m. Защищает высоту дерева от одиночного выброса ЦМД."
                  >
                    <NumberInput value={p.stats.height_trim} step={0.01} min={0} max={0.5} onChange={(v) => set('stats', { ...p.stats, height_trim: v })} className="w-28" />
                  </Field>
                </div>
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Категория рубки */}
      <Card>
        <CardPad>
          <Accordion title="Категория рубки" defaultOpen={false}>
            <div className="space-y-4">
              <Checkbox checked={p.logging_category.enabled} onChange={(v) => set('logging_category', { ...p.logging_category, enabled: v })} label="Определять категории" />
              <div className={`space-y-4 ${p.logging_category.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <div className="flex flex-wrap gap-5">
                  <Radio checked={p.logging_category.algorithm === 'threshold'} onChange={() => set('logging_category', { ...p.logging_category, algorithm: 'threshold' })} label="Пороговые правила" />
                  <div className="flex items-center gap-1">
                    <Radio checked={p.logging_category.algorithm === 'linear'} onChange={() => set('logging_category', { ...p.logging_category, algorithm: 'linear' })} label="Линейная модель" />
                    <InfoHint text="Логистическая регрессия по признакам [dist, diam, hght]. Обучается на размеченных данных. Классы: 1 — рубка, 2 — отложить, 3 — оставить." />
                  </div>
                </div>
                {p.logging_category.algorithm === 'threshold' && p.logging_category.thresholds && (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <Field label="hght <"><NumberInput value={p.logging_category.thresholds.hght} onChange={(v) => set('logging_category', { ...p.logging_category, thresholds: { ...p.logging_category.thresholds!, hght: v } })} /></Field>
                    <Field label="dist >"><NumberInput value={p.logging_category.thresholds.dist_far} onChange={(v) => set('logging_category', { ...p.logging_category, thresholds: { ...p.logging_category.thresholds!, dist_far: v } })} /></Field>
                    <Field label="dist ≥"><NumberInput value={p.logging_category.thresholds.dist_near} onChange={(v) => set('logging_category', { ...p.logging_category, thresholds: { ...p.logging_category.thresholds!, dist_near: v } })} /></Field>
                    <Field label="diam <"><NumberInput value={p.logging_category.thresholds.diam} onChange={(v) => set('logging_category', { ...p.logging_category, thresholds: { ...p.logging_category.thresholds!, diam: v } })} /></Field>
                  </div>
                )}

                {/* Таблица категорий 4×3 */}
                <div>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Таблица категорий рубки
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-slate-500">
                          <th className="py-2 pr-3 font-medium">Категория</th>
                          <th className="py-2 px-3 font-medium">Высота дерева</th>
                          <th className="py-2 px-3 font-medium">Уклон</th>
                          <th className="py-2 px-3 font-medium">Плотность</th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.logging_category.table.rows.map((row, i) => (
                          <tr key={i} className="border-b border-slate-100">
                            <td className="py-2 pr-3 text-slate-700">{row.category}</td>
                            <td className="py-2 px-3">
                              <NumberInput
                                value={row.height}
                                step={0.1}
                                disabled={!p.logging_category.enabled}
                                onChange={(v) => {
                                  const rows = [...p.logging_category.table.rows]
                                  rows[i] = { ...rows[i], height: v }
                                  set('logging_category', { ...p.logging_category, table: { rows } })
                                }}
                              />
                            </td>
                            <td className="py-2 px-3">
                              <NumberInput
                                value={row.slope}
                                step={0.1}
                                disabled={!p.logging_category.enabled}
                                onChange={(v) => {
                                  const rows = [...p.logging_category.table.rows]
                                  rows[i] = { ...rows[i], slope: v }
                                  set('logging_category', { ...p.logging_category, table: { rows } })
                                }}
                              />
                            </td>
                            <td className="py-2 px-3">
                              <NumberInput
                                value={row.density}
                                step={0.05}
                                disabled={!p.logging_category.enabled}
                                onChange={(v) => {
                                  const rows = [...p.logging_category.table.rows]
                                  rows[i] = { ...rows[i], density: v }
                                  set('logging_category', { ...p.logging_category, table: { rows } })
                                }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>
    </div>
  )
}