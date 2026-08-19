import { useMemo, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultForestParams } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, Input, InfoHint, Select } from '@/components/ui/controls'
import { ModuleHeader, SMOOTHING_BY_PRESET } from '@/components/ui/ModuleHeader'
import { RunSetup } from '@/components/ui/RunSetup'
import { Play } from 'lucide-react'
import type { ForestParams, Job, ReliefParams, SmoothingPreset, ResolutionPreset, VoidFillMethod, LoggingCategoryParams } from '@/api/types'
import { defaultJobName, availableNames, forestRunTiles, reliefCompleteness, inheritedSelection } from '@/lib/jobs'
import { generateTilesFromNames } from '@/lib/tiles'
import { checkDependencies, hasAfs } from '@/lib/dependencies'
import { withPlural, TILES } from '@/lib/plural'
import { Notice } from '@/components/ui/Notice'
import { diffParams } from '@/lib/params'

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
    logging_category: {
      ...d.logging_category, ...fp.logging_category,
      slope_rule: { ...d.logging_category.slope_rule, ...fp.logging_category?.slope_rule },
      height_limits_m: fp.logging_category?.height_limits_m ?? d.logging_category.height_limits_m,
    },
  }
}

export default function Forest() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
  const [p, setP] = useState<ForestParams>(() =>
    withDefaults((location.state as { retryParams?: ForestParams } | null)?.retryParams)
  )
  const [jobName, setJobName] = useState(() => defaultJobName('forest', jobs, projectId ?? ''))
  const inputTiles = useProjectStore((s) => (projectId ? s.inputTiles[projectId] : undefined))
  // Набор доступных тайлов задаёт выбранная сессия «Рельефа», поэтому выбор
  // пересобирается при её смене, а не один раз при монтировании.
  const [selectedTiles, setSelectedTiles] = useState<string[]>([])
  const set = <K extends keyof ForestParams>(k: K, v: ForestParams[K]) => setP((s) => ({ ...s, [k]: v }))
  const setLogging = (patch: Partial<LoggingCategoryParams>) =>
    setP((s) => ({ ...s, logging_category: { ...s.logging_category, ...patch } }))
  const setHeightLimit = (i: 0 | 1 | 2, v: number) =>
    setP((s) => {
      const limits = [...s.logging_category.height_limits_m] as [number, number, number]
      limits[i] = v
      return { ...s, logging_category: { ...s.logging_category, height_limits_m: limits } }
    })

  // Пресет сглаживания задаёт sigma; в режиме «Пользовательское» её вводят руками.
  const handleSmoothingPreset = (v: SmoothingPreset) =>
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

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      name: jobName.trim() || defaultJobName('forest', jobs, projectId),
      project_id: projectId, type: 'forest', status: 'queued', progress: 0,
      tiles_total: effectiveSelected.length, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [],
      tiles: generateTilesFromNames('forest', effectiveSelected),
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

  const [expert, setExpert] = useState(false)
  const changes = useMemo(() => diffParams(p, defaultForestParams), [p])

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  // Результаты «Рельефа» текущего проекта: показываем все сессии, где посчитан
  // хотя бы один тайл. Отсеивать неполные нельзя — по ним нужно показать, каких
  // именно данных не хватает.
  const reliefJobs = projectId
    ? jobs.filter((j) => j.project_id === projectId && j.type === 'relief' && j.tiles.some((t) => t.status === 'done'))
    : []

  const useSlopeMap = p.logging_category.enabled && p.logging_category.slope_rule.enabled
  const selectedJob = reliefJobs.find((j) => (j.session_id ?? j.id) === p.dsm_source.system_session_id)

  // Отдельного выбора производных рельефа нет: они подставляются из той же
  // сессии, что и ЦММ. Держим derivatives_source синхронным с dsm_source.
  const setDsmSession = (sessionId: string | undefined) => {
    setP((s) => ({
      ...s,
      dsm_source: { ...s.dsm_source, system_session_id: sessionId },
      derivatives_source: { ...s.derivatives_source, kind: s.dsm_source.kind, system_session_id: sessionId },
    }))
    const next = reliefJobs.find((j) => (j.session_id ?? j.id) === sessionId)
    const nextAvailable = availableNames(
      forestRunTiles(inputTiles ?? [], reliefCompleteness(next, useSlopeMap), !!sessionId),
    )
    setSelectedTiles(inheritedSelection(projectId ?? '', jobs, nextAvailable).names)
  }

  // Какие производные реально посчитаны в выбранной сессии — показываем, чтобы
  // выбор ЦММ не тянул за собой молчаливо пустой набор производных.
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

  // Полнота выбранной сессии и, как следствие, набор тайлов, доступных модулю.
  const completeness = useMemo(() => reliefCompleteness(selectedJob, useSlopeMap), [selectedJob, useSlopeMap])
  const runTiles = useMemo(
    () => forestRunTiles(inputTiles ?? [], completeness, !!selectedJob),
    [inputTiles, completeness, selectedJob],
  )

  // Выбор мог быть сделан до того, как набор доступных тайлов сузился —
  // например, при включении правила по уклону в сессии без карты уклонов.
  const effectiveSelected = useMemo(() => {
    const available = new Set(availableNames(runTiles))
    return selectedTiles.filter((n) => available.has(n))
  }, [selectedTiles, runTiles])

  const deps = checkDependencies(projectId || '', 'forest', { dsm_source: p.dsm_source })
  const runTooltip = deps.ok
    ? effectiveSelected.length === 0 ? 'Не выбрано ни одного тайла для расчёта' : undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Рассчитайте на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

  // Детекция крон идёт по ортофотоплану: без АФС расчёт недоступен.
  const afsAvailable = hasAfs(projectId || '')
  const detectionEnabled = p.detection.enabled && afsAvailable

  const inherited = useMemo(
    () => inheritedSelection(projectId ?? '', jobs, availableNames(runTiles)),
    [projectId, jobs, runTiles],
  )

  const runSummary = useMemo(() => {
    const outputs = [
      p.cmd.enabled && 'ЦМД',
      p.cmd.channels.intensity && 'интенсивность',
      p.cmd.channels.density && 'плотность точек',
      detectionEnabled && 'вершины и кроны',
      p.stats.enabled && detectionEnabled && 'статистики по сегментам',
      p.logging_category.enabled && 'категории рубки',
      p.cmd.save_classified_las && 'классифицированное облако',
    ].filter(Boolean) as string[]
    const lines = [
      `Выходы: ${outputs.join(', ') || 'ничего не выбрано'}`,
      `Пороги ярусов: поверхность ${p.cmd.threshold_surface} м, кустарник ${p.cmd.threshold_shrub} м`,
    ]
    if (detectionEnabled) {
      lines.push(`Окно поиска вершин: ${p.detection.peak_size_m} м · высоты ${p.detection.min_height_m}–${p.detection.max_height_m} м`)
    }
    if (p.logging_category.enabled) {
      const [h0, h1, h2] = p.logging_category.height_limits_m
      lines.push(
        `Категории рубки: ≤${h0} / ≤${h1} / ≤${h2} / >${h2} м` +
          (p.logging_category.slope_rule.enabled ? ` · уклон >${p.logging_category.slope_rule.threshold_deg}° → 3` : ''),
      )
    }
    return lines
  }, [p, detectionEnabled])

  // Границы категорий обязаны возрастать: иначе интервал схлопывается и
  // категория никогда не встретится в результате.
  const [h0, h1, h2] = p.logging_category.height_limits_m
  const limitsAscending = h0 < h1 && h1 < h2

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
        <Button onClick={handleRun} disabled={!deps.ok || effectiveSelected.length === 0} title={runTooltip}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {!deps.ok && (
        <Notice
          variant="warning"
          title={`Не хватает: ${deps.missing.map((m) => m.layer).join(', ')}`}
          action={`Где взять: вкладка «${deps.missing.map((m) => m.tab).join('», «')}»`}
        />
      )}

      {/* Шапка модуля: СК, сглаживание, разрешение + переключатели источника */}
      <ModuleHeader
        projectId={projectId ?? ''}
        smoothingPreset={p.smoothing_preset}
        resolutionPreset={p.output_resolution_preset}
        onSmoothingChange={handleSmoothingPreset}
        onResolutionChange={(v: ResolutionPreset) => set('output_resolution_preset', v)}
        customResolutionM={p.output_resolution_m}
        onCustomResolutionChange={(v) => set('output_resolution_m', v)}
        expert={expert}
        onExpertChange={setExpert}
        changes={changes}
        onReset={() => setP(defaultForestParams)}
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
            {reliefJobs.map((j) => (
              <option key={j.id} value={j.session_id ?? j.id}>
                {j.name} · готово {j.tiles_done} из {j.tiles_total} · {j.session_id ?? j.id}
              </option>
            ))}
          </Select>
          {reliefJobs.length === 0 ? (
            <p className="hint-base mt-1.5">Нет рассчитанных сессий «Рельефа»</p>
          ) : selectedDerivatives ? (
            <p className="hint-base mt-1.5">
              Производные рельефа подставляются из этой же сессии:{' '}
              {selectedDerivatives.length ? selectedDerivatives.join(', ') : 'в сессии не рассчитаны'}
            </p>
          ) : (
            <p className="hint-base mt-1.5">Производные рельефа подставляются из выбранной сессии автоматически</p>
          )}

        </div>

        {/* Неполнота сессии — на всю ширину: в колонке выбора текст переносился
            по три слова. Поимённый разбор — ниже, в блоке «Запуск расчёта»,
            там он стоит рядом со списком тайлов. */}
        {completeness.incompleteTiles.length > 0 && (
          <Notice
            variant="danger"
            className="mt-3"
            title={`Не хватает данных сессии: «Древостою» доступно ${completeness.readyTiles.length} из ${withPlural(completeness.readyTiles.length + completeness.incompleteTiles.length, TILES)}`}
            action="Разбор по каждому тайлу — ниже, в блоке «Запуск расчёта»"
          >
            {completeness.missingLayers.length > 0 && (
              <div>
                В сессии не построена {completeness.missingLayers.join(', ')} — пересчитайте
                «Рельеф» с этим слоем либо выберите другую сессию.
              </div>
            )}
          </Notice>
        )}
      </ModuleHeader>

      <RunSetup
        name={jobName}
        onNameChange={setJobName}
        tiles={runTiles}
        selected={effectiveSelected}
        onSelectedChange={setSelectedTiles}
        inheritedFrom={inherited.from}
        summary={runSummary}
      />

      {/* ЦМД */}
      <Card>
        <CardPad>
          <Accordion title="Цифровая модель древостоя" badge="ЦМД">
            <div className="space-y-4">
              <Checkbox checked={p.cmd.enabled} onChange={(v) => set('cmd', { ...p.cmd, enabled: v })} label="Формировать ЦМД" />
              <div className={`space-y-4 ${p.cmd.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <Field label="Агрегация точек" tooltip="Как высоты точек сводятся в ячейку полога: max — верхняя точка (поведение легаси), mean — среднее, idw — взвешенное по расстоянию.">
                      <Select
                        value={p.cmd.output_type}
                        onChange={(e) => set('cmd', { ...p.cmd, output_type: e.target.value as 'max' | 'mean' | 'idw' })}
                      >
                        <option value="max">max (верхняя точка)</option>
                        <option value="mean">mean (среднее)</option>
                        <option value="idw">idw (взвешенное)</option>
                      </Select>
                    </Field>
                    <Field label="Поверхность (м)" tooltip="Высота точек, относимая к поверхности (класс 3). Точки ниже этого порога считаются поверхностью земли.">
                      <NumberInput value={p.cmd.threshold_surface} step={0.1} min={0} onChange={(v) => set('cmd', { ...p.cmd, threshold_surface: v })} />
                    </Field>
                    <Field label="Кустарники (м)" tooltip="Верхняя граница кустарникового яруса (класс 4). Выше — древесный ярус (класс 5). Той же границей разделяются найденные вершины на кустарник и древостой.">
                      <NumberInput value={p.cmd.threshold_shrub} step={0.5} min={0} onChange={(v) => set('cmd', { ...p.cmd, threshold_shrub: v })} />
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
                {expert && (
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
                )}
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
                <Notice
                  variant="warning"
                  title="Не хватает: АФС — детекция крон идёт по ортофотоплану"
                  action="Где взять: вкладка «Загрузка данных». Остальные блоки модуля считаются по ВЛС и ЦММ."
                />
              )}
              <div className={`space-y-4 ${detectionEnabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <p className="hint-base">
                  Вершины ищутся локальным максимумом, границы крон — водоразделом по поверхности
                  стоимости. Нейросетевого режима в расчётном ядре нет.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
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
                    <Field label="Сглаживание, пикс" tooltip="Радиус медианного ядра, которым ЦМД сглаживается перед поиском максимумов. 0 — без сглаживания.">
                      <NumberInput value={p.detection.smooth_radius_px} min={0} onChange={(v) => set('detection', { ...p.detection, smooth_radius_px: v })} />
                    </Field>
                  </div>
                  <div className={`mt-3 ${expert ? '' : 'hidden'}`}>
                    <span className="inline-flex items-center gap-1.5">
                      <Checkbox
                        checked={p.detection.height_from_smoothed}
                        onChange={(v) => set('detection', { ...p.detection, height_from_smoothed: v })}
                        label="Высоту дерева снимать со сглаженного растра"
                        disabled={p.detection.smooth_radius_px === 0}
                      />
                      <InfoHint text="Поведение легаси СИМА 1.44. Медианный фильтр срезает макушки, поэтому высота занижается: на кроне 23 м радиус 1 пикс даёт 21.8 м. Выключено — высота снимается с исходной ЦМД." />
                    </span>
                  </div>
                </div>

                {/* Корректировка вершин по АФС */}
                {expert && (
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
                )}

                {/* Поверхность стоимости водораздела */}
                {expert && (
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
                )}
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Статистики ТЛО */}
      {expert && (
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

      )}

      {/* Категория рубки */}
      <Card>
        <CardPad>
          <Accordion title="Категории рубки леса" defaultOpen={false}>
            <div className="space-y-4">
              <Checkbox
                checked={p.logging_category.enabled}
                onChange={(v) => setLogging({ enabled: v })}
                label="Определять категории"
              />
              <div className={`space-y-4 ${p.logging_category.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                {/* Высота дерева по категориям */}
                <div>
                  <div className="mb-2 flex items-center gap-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Высота дерева по категориям
                    </span>
                    <InfoHint text="Границы берутся с карты высот растительности (ЦМД) и заданы как «до, включительно». Каждая следующая категория начинается сразу за границей предыдущей." />
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {([0, 1, 2] as const).map((i) => (
                      <Field key={i} label={`${i} категория, до (м)`}>
                        <NumberInput
                          value={p.logging_category.height_limits_m[i]}
                          step={0.5}
                          min={0}
                          onChange={(v) => setHeightLimit(i, v)}
                        />
                      </Field>
                    ))}
                    <Field
                      label="3 категория"
                      tooltip="Верхняя граница не задаётся: в третью категорию попадает всё, что выше границы второй."
                    >
                      <div className="flex h-9 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-600">
                        более {p.logging_category.height_limits_m[2]} м
                      </div>
                    </Field>
                  </div>
                  {!limitsAscending && (
                    <p className="mt-2 text-xs text-amber-600">
                      Границы должны возрастать: 0 категория &lt; 1 категория &lt; 2 категория.
                      Иначе часть категорий останется пустой.
                    </p>
                  )}
                </div>

                {/* Правило по уклону */}
                <div className="rounded-lg border border-slate-200 p-3">
                  <span className="inline-flex items-center gap-1.5">
                    <Checkbox
                      checked={p.logging_category.slope_rule.enabled}
                      onChange={(v) => setLogging({ slope_rule: { ...p.logging_category.slope_rule, enabled: v } })}
                      label="Учитывать карту уклонов"
                    />
                    <InfoHint text="Карта уклонов берётся из выбранной сессии «Рельефа». Участок круче порога относится к 3 категории независимо от высоты растительности." />
                  </span>
                  <div className={`mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4 ${p.logging_category.slope_rule.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                    <Field label="Уклон более (°) → 3 категория">
                      <NumberInput
                        value={p.logging_category.slope_rule.threshold_deg}
                        step={1}
                        min={0}
                        max={90}
                        onChange={(v) => setLogging({ slope_rule: { ...p.logging_category.slope_rule, threshold_deg: v } })}
                      />
                    </Field>
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