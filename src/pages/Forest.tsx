import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultForestParams } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, Radio, NumberInput, Field, Input, InfoHint } from '@/components/ui/controls'
import { Play } from 'lucide-react'
import type { ForestParams, Job } from '@/api/types'

export default function Forest() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { settings } = useSettingsStore()
  const addJob = useProjectStore((s) => s.addJob)
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
        <Button onClick={handleRun}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {/* ЦМД */}
      <Card>
        <CardPad>
          <Accordion title="Цифровая модель древостоя" badge="ЦМД">
            <div className="space-y-4">
              <Checkbox checked={p.cmd.enabled} onChange={(v) => set('cmd', { ...p.cmd, enabled: v })} label="Формировать ЦМД" />
              <div className={`space-y-4 ${p.cmd.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
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
                <div className="flex flex-wrap gap-4">
                  <Checkbox checked={p.cmd.channels.chm} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, chm: v } })} label="CHM (высота крон)" />
                  <Checkbox checked={p.cmd.channels.its} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, its: v } })} label="ITS (интенсивность)" />
                  <Checkbox checked={p.cmd.channels.den} onChange={(v) => set('cmd', { ...p.cmd, channels: { ...p.cmd.channels, den: v } })} label="DEN (плотность)" />
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
              <div className="flex flex-wrap gap-5">
                <Radio checked={p.detection.method === 'yolov5'} onChange={() => set('detection', { ...p.detection, method: 'yolov5' })} label="Нейросеть" />
                <Radio checked={p.detection.method === 'watershed'} onChange={() => set('detection', { ...p.detection, method: 'watershed' })} label="Водораздел" />
                <Radio checked={p.detection.method === 'both'} onChange={() => set('detection', { ...p.detection, method: 'both' })} label="Оба метода" />
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Field label="Размер тайла (px)"><NumberInput value={p.detection.sample_size} onChange={(v) => set('detection', { ...p.detection, sample_size: v })} /></Field>
                <Field label="Перекрытие (px)"><NumberInput value={p.detection.bound} onChange={(v) => set('detection', { ...p.detection, bound: v })} /></Field>
                <Field label="Сезон">
                  <select
                    className="input-base"
                    value={p.detection.season}
                    onChange={(e) => set('detection', { ...p.detection, season: e.target.value as 'summer' | 'winter' })}
                  >
                    <option value="summer">Лето</option>
                    <option value="winter">Зима</option>
                  </select>
                </Field>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                Каталог весов: <code className="text-slate-700">{settings.model_paths.treecanopy || 'не задан'}</code>
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
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Доп. слои */}
      <Card>
        <CardPad>
          <Accordion title="Дополнительные слои" defaultOpen={false}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Checkbox checked={p.extras.fire} onChange={(v) => set('extras', { ...p.extras, fire: v })} label="Гари" />
                <div className={`mt-2 grid grid-cols-2 gap-2 ${p.extras.fire ? '' : 'opacity-40 pointer-events-none'}`}>
                  <Field label="Разрешение"><NumberInput value={p.extras.fire_res} step={0.1} onChange={(v) => set('extras', { ...p.extras, fire_res: v })} /></Field>
                  <Field label="Сглаживание"><NumberInput value={p.extras.fire_sm} step={0.1} onChange={(v) => set('extras', { ...p.extras, fire_sm: v })} /></Field>
                </div>
              </div>
              <div>
                <Checkbox checked={p.extras.wind} onChange={(v) => set('extras', { ...p.extras, wind: v })} label="Ветровалы" />
                <div className={`mt-2 grid grid-cols-2 gap-2 ${p.extras.wind ? '' : 'opacity-40 pointer-events-none'}`}>
                  <Field label="Разрешение"><NumberInput value={p.extras.wind_res} step={0.1} onChange={(v) => set('extras', { ...p.extras, wind_res: v })} /></Field>
                  <Field label="Сглаживание"><NumberInput value={p.extras.wind_sm} step={0.1} onChange={(v) => set('extras', { ...p.extras, wind_sm: v })} /></Field>
                </div>
              </div>
              <Checkbox checked={p.extras.tlo} onChange={(v) => set('extras', { ...p.extras, tlo: v })} label="Сохранить TLO" />
              <div>
                <Checkbox checked={p.extras.peaks} onChange={(v) => set('extras', { ...p.extras, peaks: v })} label="Пики" />
                {p.extras.peaks && (
                  <div className="mt-2"><Field label="Размер"><NumberInput value={p.extras.peak_size} onChange={(v) => set('extras', { ...p.extras, peak_size: v })} /></Field></div>
                )}
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>
    </div>
  )
}