import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultWaterParams } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox, NumberInput, Field, InfoHint } from '@/components/ui/controls'
import { Play } from 'lucide-react'
import type { WaterParams, Job } from '@/api/types'

export default function Water() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const addJob = useProjectStore((s) => s.addJob)
  const [p, setP] = useState<WaterParams>(() =>
    (location.state as { retryParams?: WaterParams } | null)?.retryParams ?? defaultWaterParams
  )
  const set = <K extends keyof WaterParams>(k: K, v: WaterParams[K]) => setP((s) => ({ ...s, [k]: v }))

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      project_id: projectId, type: 'water', status: 'queued', progress: 0,
      tiles_total: 12, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [], tiles: [],
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
          <h1>Вода</h1>
          <p className="mt-1 text-sm text-slate-500">
            Параметры обработки
            {isRetry && <span className="ml-2 text-brand-600">· повтор с новыми параметрами (новая сессия)</span>}
          </p>
        </div>
        <Button onClick={handleRun}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {/* Сегментация вод */}
      <Card>
        <CardPad>
          <Accordion title="Сегментация поверхностных вод">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Field label="Порог" tooltip="Порог бинаризации маски вероятности. Значения выше порога → вода, ниже → не вода. По умолчанию 0.6.">
                  <NumberInput value={p.segment.threshold} step={0.05} min={0} max={1} onChange={(v) => set('segment', { ...p.segment, threshold: v })} />
                </Field>
                <Field label="Размер тайла"><NumberInput value={p.segment.sample_size} min={1} onChange={(v) => set('segment', { ...p.segment, sample_size: v })} /></Field>
                <Field label="Перекрытие"><NumberInput value={p.segment.bound} min={0} onChange={(v) => set('segment', { ...p.segment, bound: v })} /></Field>
                <Field label="Разрешение (м)"><NumberInput value={p.segment.resolution} step={0.1} min={0} onChange={(v) => set('segment', { ...p.segment, resolution: v })} /></Field>
              </div>
              <Field label="Сглаживание">
                <NumberInput value={p.segment.smooth} step={0.1} onChange={(v) => set('segment', { ...p.segment, smooth: v })} className="w-32" />
              </Field>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Болота */}
      <Card>
        <CardPad>
          <Accordion title="Болота" defaultOpen={false}>
            <div className="space-y-4">
              <Checkbox checked={p.swamp.segment} onChange={(v) => set('swamp', { ...p.swamp, segment: v })} label="Сегментация болот" />
              <div className={`grid grid-cols-2 gap-3 sm:grid-cols-3 ${p.swamp.segment ? '' : 'opacity-40 pointer-events-none'}`}>
                <Field label="Порог"><NumberInput value={p.swamp.threshold} step={0.05} onChange={(v) => set('swamp', { ...p.swamp, threshold: v })} /></Field>
                <Field label="Сглаживание"><NumberInput value={p.swamp.smooth} step={0.1} onChange={(v) => set('swamp', { ...p.swamp, smooth: v })} /></Field>
                <Field label="Разрешение (м)"><NumberInput value={p.swamp.resolution} step={0.1} onChange={(v) => set('swamp', { ...p.swamp, resolution: v })} /></Field>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={p.swamp.classify}
                  onChange={(v) => set('swamp', { ...p.swamp, classify: v })}
                  label="Классификация по TPI"
                  disabled={!p.swamp.segment}
                />
                <InfoHint text="Классификация болот по индексу TPI: среднее TPI > 0 → верховое (класс 1), ≤ 0 → низинное (класс 0)." />
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>

      {/* Охранные зоны */}
      <Card>
        <CardPad>
          <Accordion title="Охранные зоны" defaultOpen={false}>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Прибрежная полоса (м)"><NumberInput value={p.buffers.coastal_m} onChange={(v) => set('buffers', { ...p.buffers, coastal_m: v })} /></Field>
              <Field label="Защитная полоса (м)"><NumberInput value={p.buffers.protective_m} onChange={(v) => set('buffers', { ...p.buffers, protective_m: v })} /></Field>
              <Field label="Водоохранная зона (м)"><NumberInput value={p.buffers.water_protection_m} onChange={(v) => set('buffers', { ...p.buffers, water_protection_m: v })} /></Field>
            </div>
          </Accordion>
        </CardPad>
      </Card>
    </div>
  )
}