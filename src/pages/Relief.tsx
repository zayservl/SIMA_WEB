import { useMemo, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultReliefParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, InfoHint, Select, Input } from '@/components/ui/controls'
import { ModuleHeader, SMOOTHING_BY_PRESET } from '@/components/ui/ModuleHeader'
import { METHOD_TOOLTIPS } from '@/lib/methodTooltips'
import { RunSetup } from '@/components/ui/RunSetup'
import { Play, AlertTriangle } from 'lucide-react'
import type { ReliefParams, Job, SmoothingPreset, FilterMethod, VoidFillMethod } from '@/api/types'
import { defaultJobName, moduleRunTiles, availableNames, inheritedSelection } from '@/lib/jobs'
import { diffParams } from '@/lib/params'
import { generateTilesFromNames } from '@/lib/tiles'
import { checkDependencies } from '@/lib/dependencies'

const FILTER_METHOD_LABELS: Record<FilterMethod, string> = {
  smrf: 'SMRF',
  manual: 'Ручная',
  stat: 'Статистическая',
  range: 'Перцентильная',
  kmeans: 'Отсев выбросов',
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
    dtm: { ...d.dtm, ...rp.dtm },
    dsm: { ...d.dsm, ...rp.dsm },
    derivatives: { ...d.derivatives, ...rp.derivatives },
    heights: { ...d.heights, ...rp.heights },
    vectors: { ...d.vectors, ...rp.vectors },
  }
}

// Параметры механизма заполнения пустот (backend: holes.fill_voids). Одинаковый
// набор у ЦМР и ЦММ, поэтому вынесен в общий блок.
function VoidFillControls({ method, passes, hydro, onChange }: {
  method: VoidFillMethod
  passes: number
  hydro: boolean
  onChange: (patch: { method?: VoidFillMethod; passes?: number; hydro?: boolean }) => void
}) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Метод заполнения" tooltip="laplace — решение уравнения Лапласа в пустоте: поверхность гладкая по построению. idw — GDALFillNodata: быстрее, но даёт радиальные лучи внутрь крупных пустот и не дотягивается дальше радиуса поиска.">
          <Select value={method} onChange={(e) => onChange({ method: e.target.value as VoidFillMethod })}>
            <option value="laplace">laplace (гладко)</option>
            <option value="idw">idw (быстро)</option>
          </Select>
        </Field>
        <Field label="Проходов заполнения" tooltip="Маска пустот пересчитывается после каждого прохода: часть пустот замыкается в дыру только после заполнения соседних. 1 — однопроходное поведение легаси.">
          <NumberInput value={passes} min={1} onChange={(v) => onChange({ passes: v })} />
        </Field>
      </div>
      <span className="inline-flex items-center gap-1.5">
        <Checkbox checked={hydro} onChange={(v) => onChange({ hydro: v })} label="Гидровыравнивание водоёмов" />
        <InfoHint text="Пустоты, распознанные как водоёмы, получают плоскую отметку вместо интерполяции (3DEP hydro-flattening). На тайлах без водоёмов может ошибочно выровнять крупную пустоту съёмки и внести ошибку в метры." />
      </span>
    </>
  )
}

export default function Relief() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useSettingsStore()
  const projects = useProjectStore((s) => s.projects)
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
  const project = projects.find((p) => p.id === projectId)
  const [p, setP] = useState<ReliefParams>(() =>
    withDefaults((location.state as { retryParams?: ReliefParams } | null)?.retryParams)
  )
  const [jobName, setJobName] = useState(() => defaultJobName('relief', jobs, projectId ?? ''))
  const inputTiles = useProjectStore((s) => (projectId ? s.inputTiles[projectId] : undefined))
  const runTiles = useMemo(() => moduleRunTiles('relief', inputTiles ?? []), [inputTiles])
  // Набор наследуется от прошлого расчёта проекта: пользователь уже выбрал
  // интересующую его часть участка, отмечать её заново незачем.
  const inherited = useMemo(
    () => inheritedSelection(projectId ?? '', jobs, availableNames(runTiles)),
    [projectId, jobs, runTiles],
  )
  const [selectedTiles, setSelectedTiles] = useState<string[]>(() => inherited.names)
  const set = <K extends keyof ReliefParams>(k: K, v: ReliefParams[K]) => setP((s) => ({ ...s, [k]: v }))

  // Сечения вводятся строкой: набор шагов, а не фиксированное число полей.
  // В параметры уходят только положительные числа, разбор — по потере фокуса.
  const [horizontalsText, setHorizontalsText] = useState(() => p.vectors.horizontals.join(', '))
  const [horizontalsInvalid, setHorizontalsInvalid] = useState(false)
  const commitHorizontals = () => {
    const parts = horizontalsText.split(/[,;\s]+/).filter(Boolean)
    const values = parts.map((t) => parseFloat(t.replace(',', '.'))).filter((v) => isFinite(v) && v > 0)
    const unique = [...new Set(values)].sort((a, b) => a - b)
    setHorizontalsInvalid(unique.length !== parts.length)
    setP((s) => ({ ...s, vectors: { ...s.vectors, horizontals: unique } }))
    setHorizontalsText(unique.join(', '))
  }

  // Маппинг предустановок сглаживания → sigma/expert-параметры. В режиме
  // «Пользовательское» sigma не подменяется — её задаёт пользователь.
  const handleSmoothingPreset = (v: SmoothingPreset) => {
    setP((s) => ({
      ...s,
      smoothing_preset: v,
      smoothing: {
        ...s.smoothing,
        enabled: v !== 'off',
        // «Пользовательское» и «Без сглаживания» значения фильтра не трогают:
        // при возврате к пресету они перезапишутся, а до тех пор сохраняются.
        ...(v === 'custom' || v === 'off' ? {} : SMOOTHING_BY_PRESET[v]),
      },
    }))
  }

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      name: jobName.trim() || defaultJobName('relief', jobs, projectId),
      project_id: projectId, type: 'relief', status: 'queued', progress: 0,
      tiles_total: selectedTiles.length, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [],
      tiles: generateTilesFromNames('relief', selectedTiles),
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

  // Сводка «что пойдёт в расчёт»: собрать это, пролистывая аккордеоны, долго.
  const runSummary = useMemo(() => {
    const outputs = [
      'ЦМР',
      p.dsm.enabled && 'ЦММ',
      p.derivatives.slopes && 'уклоны',
      p.derivatives.aspect && 'экспозиции',
      p.derivatives.tpi && 'TPI',
      p.vectors.horizontals.length > 0 && `горизонтали ${p.vectors.horizontals.join('/')} м`,
      p.heights.enabled && 'отметки высот',
      p.vectors.tin && 'TIN',
      p.save_measured_mask && 'маска измеренных ячеек',
    ].filter(Boolean) as string[]
    const smoothing = p.smoothing.enabled
      ? `сглаживание σ ${p.smoothing.sigma}, окно ${p.smoothing.window}`
      : 'без сглаживания'
    return [
      `Выходы: ${outputs.join(', ')}`,
      `Классификация: ${FILTER_METHOD_LABELS[p.filter_method]} · ${smoothing}`,
      `Заполнение пустот: ${p.derivatives.fill_method}, ${p.derivatives.fill_passes} прох.` +
        (p.derivatives.hydro_flatten ? ', гидровыравнивание' : ''),
    ]
  }, [p])

  // Экспертная настройка скрыта по умолчанию: в типовой работе трогают метод
  // классификации, состав выходов и сглаживание, а не радиусы заполнения.
  const [expert, setExpert] = useState(false)
  const changes = useMemo(() => diffParams(p, defaultReliefParams), [p])

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  const deps = checkDependencies(projectId || '', 'relief')
  const runTooltip = deps.ok
    ? selectedTiles.length === 0 ? 'Не выбрано ни одного тайла для расчёта' : undefined
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
        <Button onClick={handleRun} disabled={!deps.ok || selectedTiles.length === 0} title={runTooltip}><Play className="h-4 w-4" /> Запустить</Button>
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
        expert={expert}
        onExpertChange={setExpert}
        changes={changes}
        onReset={() => { setP(defaultReliefParams); setHorizontalsText(defaultReliefParams.vectors.horizontals.join(', ')) }}
      />

      <RunSetup
        name={jobName}
        onNameChange={setJobName}
        tiles={runTiles}
        selected={selectedTiles}
        onSelectedChange={setSelectedTiles}
        inheritedFrom={inherited.from}
        summary={runSummary}
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
                  <Radio checked={p.filter_method === 'kmeans'} onChange={() => set('filter_method', 'kmeans')} label="Отсев выбросов" />
                  <InfoHint text={METHOD_TOOLTIPS.kmeans} />
                </span>
              </div>

              {p.filter_method === 'manual' && (
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Z min"><NumberInput value={p.filter.spm_min || 0} onChange={(v) => set('filter', { ...p.filter, spm_min: v })} /></Field>
                  <Field label="Z max"><NumberInput value={p.filter.spm_max || 1000} onChange={(v) => set('filter', { ...p.filter, spm_max: v })} /></Field>
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
                  <Field label="Соседей в выборке" tooltip="mean_k — сколько ближайших точек берётся для оценки среднего расстояния.">
                    <NumberInput value={p.filter.mean_k || 8} onChange={(v) => set('filter', { ...p.filter, mean_k: v })} />
                  </Field>
                  <Field label="Множитель СКО" tooltip="multiplier — во сколько стандартных отклонений укладывается «нормальная» точка.">
                    <NumberInput value={p.filter.mult || 2} step={0.1} onChange={(v) => set('filter', { ...p.filter, mult: v })} />
                  </Field>
                </div>
              )}

              <p className="hint-base">
                Готовая классификация входного LAS (класс 2 по ASPRS) используется автоматически,
                когда она есть в файле, — отдельного метода для неё нет.
              </p>

              {p.filter_method === 'smrf' && expert && (
                <div className="border-t border-slate-100 pt-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Параметры SMRF</span>
                    <InfoHint text="Simple Morphological Filter — алгоритм выделения точек рельефа. Параметры по умолчанию: уклон 0.2, окно 16 м, порог 0.45 м, множитель 1.2." />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <Field label="Уклон" tooltip="slope — предельный уклон морфологического окна, доля. Выше него точка не считается землёй.">
                      <NumberInput value={p.smrf.slope} step={0.05} onChange={(v) => set('smrf', { ...p.smrf, slope: v })} />
                    </Field>
                    <Field label="Окно, м" tooltip="window — максимальный размер морфологического окна: задаёт наибольший объект, который фильтр снимет с поверхности земли.">
                      <NumberInput value={p.smrf.window} onChange={(v) => set('smrf', { ...p.smrf, window: v })} />
                    </Field>
                    <Field label="Порог, м" tooltip="threshold — допуск превышения над поверхностью, м. Точки выше относятся к объектам.">
                      <NumberInput value={p.smrf.threshold} step={0.05} onChange={(v) => set('smrf', { ...p.smrf, threshold: v })} />
                    </Field>
                    <Field label="Множитель порога" tooltip="scalar — во сколько раз допуск растёт с уклоном местности.">
                      <NumberInput value={p.smrf.scalar} step={0.1} onChange={(v) => set('smrf', { ...p.smrf, scalar: v })} />
                    </Field>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4">
                    <Checkbox checked={p.smrf.elm} onChange={(v) => set('smrf', { ...p.smrf, elm: v })} label="Отсев низких выбросов (ELM)" />
                    <Checkbox checked={p.smrf.outlier} onChange={(v) => set('smrf', { ...p.smrf, outlier: v })} label="Отсев статистических выбросов" />
                    <span className="inline-flex items-center gap-2">
                      <Checkbox checked={p.smrf.cut_smrf} onChange={(v) => set('smrf', { ...p.smrf, cut_smrf: v })} label="Доп. отсечение" />
                      <InfoHint text="cut_smrf — отбросить точки, отстоящие от найденной поверхности земли дальше порога." />
                    </span>
                  </div>
                  {p.smrf.cut_smrf && (
                    <div className="mt-3 sm:max-w-xs">
                      <Field label="Порог отсечения, м" tooltip="cut_threshold — на сколько точка может отстоять от поверхности земли, оставаясь землёй.">
                        <NumberInput value={p.smrf.cut_threshold} step={0.5} min={0} onChange={(v) => set('smrf', { ...p.smrf, cut_threshold: v })} />
                      </Field>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {expert && (
      <>
      {/* ЦМР — основной выход модуля. Растеризация выполняется до заполнения
          пустот, поэтому вынесена отдельно от блока «Интерполяция». */}
      <Card>
        <CardPad>
          <Accordion title="Цифровая модель рельефа" badge="ЦМР">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Агрегация точек"
                tooltip="Как высоты ground-точек сводятся в ячейку растра (writers.gdal): idw — обратно взвешенное расстояние (умолчание сервиса), min — нижняя точка, max — верхняя, mean — среднее."
              >
                <Select
                  value={p.dtm.output_type}
                  onChange={(e) => set('dtm', { ...p.dtm, output_type: e.target.value as ReliefParams['dtm']['output_type'] })}
                >
                  <option value="idw">idw (взвешенное)</option>
                  <option value="min">min (нижняя точка)</option>
                  <option value="max">max (верхняя точка)</option>
                  <option value="mean">mean (среднее)</option>
                </Select>
              </Field>
            </div>
            <p className="hint-base mt-3">
              Заполнение пустот ЦМР задаётся ниже, в блоке «Интерполяция и экстраполяция».
            </p>
          </Accordion>
        </CardPad>
      </Card>

      </>
      )}

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
                <div className={`space-y-3 ${p.dsm.enabled && expert ? '' : 'hidden'}`}>
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
                  <VoidFillControls
                    method={p.dsm.fill_method}
                    passes={p.dsm.fill_passes}
                    hydro={p.dsm.hydro_flatten}
                    onChange={(patch) => set('dsm', {
                      ...p.dsm,
                      ...(patch.method !== undefined && { fill_method: patch.method }),
                      ...(patch.passes !== undefined && { fill_passes: patch.passes }),
                      ...(patch.hydro !== undefined && { hydro_flatten: patch.hydro }),
                    })}
                  />
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

      {/* Заполнение пустот ЦМР — единственный слой, где оно выполняется:
          уклоны и экспозиции строятся gdal.DEMProcessing из уже заполненной ЦМР. */}
      {expert && (
      <Card>
        <CardPad>
          <Accordion title="Интерполяция и экстраполяция">
            <div className="max-w-md space-y-3">
              <p className="hint-base">
                Заполнение пустот ЦМР выполняется до сглаживания и до построения производных,
                поэтому уклоны, экспозиции и TPI наследуют его результат.
              </p>
              <div className="rounded-lg border border-slate-200 p-3">
                <span className="inline-flex items-center gap-1.5">
                  <Checkbox
                    checked={p.derivatives.interpolation}
                    onChange={(v) => set('derivatives', { ...p.derivatives, interpolation: v })}
                    label="Заполнять пустоты ЦМР"
                  />
                  <InfoHint text="Заполняются внутренние дыры и пустоты не далее заданной экстраполяции от данных. Область, куда съёмка не заходила, остаётся пустой намеренно." />
                </span>
                <div className={`mt-2 space-y-3 ${p.derivatives.interpolation ? '' : 'opacity-40 pointer-events-none'}`}>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Амплитуда интерполяции" tooltip="inter_amp — радиус поиска значений при заполнении пустот обратно взвешенным расстоянием (IDW).">
                      <NumberInput value={p.derivatives.inter_amp} step={0.1} min={0} onChange={(v) => set('derivatives', { ...p.derivatives, inter_amp: v })} />
                    </Field>
                    <Field label="Экстраполяция края, м" tooltip="На сколько метров допустимо выйти за границу валидной области. 0 — заполнять только внутренние дыры: пустоты, касающиеся рамки растра, остаются незаполненными.">
                      <NumberInput value={p.derivatives.edge_extrapolation_m} step={1} min={0} onChange={(v) => set('derivatives', { ...p.derivatives, edge_extrapolation_m: v })} />
                    </Field>
                  </div>
                  <VoidFillControls
                    method={p.derivatives.fill_method}
                    passes={p.derivatives.fill_passes}
                    hydro={p.derivatives.hydro_flatten}
                    onChange={(patch) => set('derivatives', {
                      ...p.derivatives,
                      ...(patch.method !== undefined && { fill_method: patch.method }),
                      ...(patch.passes !== undefined && { fill_passes: patch.passes }),
                      ...(patch.hydro !== undefined && { hydro_flatten: patch.hydro }),
                    })}
                  />
                </div>
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      )}

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
                <Field
                  label="Сечение горизонталей, м"
                  tooltip="Шаги сечения, для каждого строится свой слой горизонталей (backend: vectors.horizontals). Значения через запятую; порядок и повторы не важны."
                  className="sm:max-w-md"
                >
                  <Input
                    value={horizontalsText}
                    onChange={(e) => setHorizontalsText(e.target.value)}
                    onBlur={commitHorizontals}
                    placeholder="0.5, 2, 5, 10"
                  />
                </Field>
                {horizontalsInvalid && (
                  <p className="mt-1 text-xs text-amber-600">
                    Приведено к {p.vectors.horizontals.join(', ') || 'пустому списку'}: оставлены
                    положительные числа без повторов.
                  </p>
                )}
              </div>
              <div className="border-t border-slate-100 pt-3">
                <Checkbox checked={p.vectors.tin} onChange={(v) => set('vectors', { ...p.vectors, tin: v })} label="TIN (DXF)" />
              </div>
              <div className="border-t border-slate-100 pt-3">
                <span className="inline-flex items-center gap-1.5">
                  <Checkbox
                    checked={p.save_measured_mask}
                    onChange={(v) => set('save_measured_mask', v)}
                    label="Сохранять маску измеренных ячеек"
                  />
                  <InfoHint text="Дополнительный растр: где отметка ЦМР получена из точек съёмки, а где достроена интерполяцией. Нужен, чтобы отличать точность построения от точности заполнения пустот." />
                </span>
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