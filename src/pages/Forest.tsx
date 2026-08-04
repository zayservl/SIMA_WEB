import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultForestParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, Input, InfoHint, Select } from '@/components/ui/controls'
import { ModuleHeader } from '@/components/ui/ModuleHeader'
import { Play, AlertTriangle } from 'lucide-react'
import type { ForestParams, Job, ReliefSource, SmoothingPreset, ResolutionPreset, ParamMode } from '@/api/types'
import { checkDependencies } from '@/lib/dependencies'

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

export default function Forest() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useSettingsStore()
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
  const [p, setP] = useState<ForestParams>(() =>
    (location.state as { retryParams?: ForestParams } | null)?.retryParams ?? defaultForestParams
  )
  const set = <K extends keyof ForestParams>(k: K, v: ForestParams[K]) => setP((s) => ({ ...s, [k]: v }))

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      project_id: projectId, type: 'forest', status: 'queued', progress: 0,
      tiles_total: 18, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [], tiles: [],
      started_at: new Date().toISOString(), params: p,
    }
    addJob(job)
    navigate(`/projects/${projectId}/tasks`)
  }

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  const deps = checkDependencies(projectId || '', 'forest', { dsm_source: p.dsm_source, derivatives_source: p.derivatives_source })
  const runTooltip = deps.ok
    ? undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Рассчитайте на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

  // Завершённые задачи рельефа в рамках текущего проекта — источник ЦМР/производных.
  const reliefJobs = projectId
    ? jobs.filter((j) => j.project_id === projectId && j.type === 'relief' && j.status === 'success')
    : []

  const setSource = (key: 'dsm_source' | 'derivatives_source', patch: Partial<ReliefSource>) =>
    setP((s) => ({ ...s, [key]: { ...s[key], ...patch } }))

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

      {/* Шапка модуля: СК, сглаживание, разрешение + переключатели источника */}
      <ModuleHeader
        projectId={projectId ?? ''}
        smoothingPreset={p.smoothing_preset}
        resolutionPreset={p.output_resolution_preset}
        onSmoothingChange={(v: SmoothingPreset) => set('smoothing_preset', v)}
        onResolutionChange={(v: ResolutionPreset) => set('output_resolution_preset', v)}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Источник ЦММ — только рассчитанная в системе сессия «Рельефа» */}
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Источник ЦММ</div>
            <Select
              value={p.dsm_source.system_session_id ?? ''}
              onChange={(e) => setSource('dsm_source', { system_session_id: e.target.value || undefined })}
            >
              <option value="">— выбрать сессию —</option>
              {reliefJobs.map((j) => (
                <option key={j.id} value={j.session_id ?? j.id}>
                  {j.session_id ?? j.id}
                </option>
              ))}
            </Select>
            {reliefJobs.length === 0 && <p className="hint-base mt-1.5">Нет завершённых сессий «Рельефа»</p>}
          </div>

          {/* Источник производных рельефа */}
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Источник производных рельефа</div>
            <Select
              value={p.derivatives_source.system_session_id ?? ''}
              onChange={(e) => setSource('derivatives_source', { system_session_id: e.target.value || undefined })}
            >
              <option value="">— выбрать сессию —</option>
              {reliefJobs.map((j) => (
                <option key={j.id} value={j.session_id ?? j.id}>
                  {j.session_id ?? j.id}
                </option>
              ))}
            </Select>
            {reliefJobs.length === 0 && <p className="hint-base mt-1.5">Нет завершённых сессий «Рельефа»</p>}
          </div>
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
                <div className="flex flex-wrap gap-4">
                  <Checkbox checked={p.cmd.channels.chm} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, chm: v } })} label="CHM (высота крон)" />
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
              <ParamModeSwitch
                mode={p.detection.mode}
                onChange={(mode) => set('detection', { ...p.detection, mode })}
                aiLabel="ИИ (нейросеть YOLOv5)"
                algorithmicLabel="Алгоритмически (водораздел)"
                aiHint="Границы сегментов крон определяет модель"
              />
              <Field label="Состояние вегетации">
                <Select
                  value={p.detection.vegetation_state}
                  onChange={(e) => set('detection', { ...p.detection, vegetation_state: e.target.value as 'active' | 'absent' })}
                >
                  <option value="active">Активная</option>
                  <option value="absent">Отсутствует</option>
                </Select>
              </Field>
              {p.detection.mode === 'ai' && (
                <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                  Каталог весов: <code className="text-slate-700">{settings.model_paths.treecanopy || 'не задан'}</code>
                </div>
              )}
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Статистики ТЛО */}
      <Card>
        <CardPad>
          <Accordion title="Статистики по сегментам крон" defaultOpen={false}>
            <div className="space-y-4">
              <Checkbox checked={p.stats.enabled} onChange={(v) => set('stats', { ...p.stats, enabled: v })} label="Собрать статистики" />
              <div className={`space-y-4 ${p.stats.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <div className="flex items-center gap-2">
                  <Field label="Перцентили (через запятую)" tooltip="Перцентили распределения высот точек внутри каждого сегмента кроны. Используются для оценки структуры древостоя." className="flex-1">
                    <Input
                      value={p.stats.percentiles.join(', ')}
                      onChange={(e) => set('stats', { ...p.stats, percentiles: e.target.value.split(',').map((x) => parseInt(x.trim())).filter((x) => !isNaN(x)) })}
                    />
                  </Field>
                </div>
                <div>
                  <span className="label-base">Шаг VCI, м</span>
                  <div className="mt-1.5 flex gap-5">
                    <Radio checked={p.stats.vci_step === 1} onChange={() => set('stats', { ...p.stats, vci_step: 1 })} label="1.0" />
                    <Radio checked={p.stats.vci_step === 0.5} onChange={() => set('stats', { ...p.stats, vci_step: 0.5 })} label="0.5" />
                  </div>
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