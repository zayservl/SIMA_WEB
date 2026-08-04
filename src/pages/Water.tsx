import { useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultWaterParams } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { NumberInput, Field, Select } from '@/components/ui/controls'
import { ModuleHeader } from '@/components/ui/ModuleHeader'
import { Play, AlertTriangle } from 'lucide-react'
import type { WaterParams, Job, ReliefParams, ResolutionPreset } from '@/api/types'
import { checkDependencies } from '@/lib/dependencies'

export default function Water() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
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

  const deps = checkDependencies(projectId || '', 'water', { cmd_source: p.cmd_source })
  const runTooltip = deps.ok
    ? undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Рассчитайте на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

  // Завершённые задачи леса в рамках текущего проекта — источник ЦМД.
  const forestJobs = projectId
    ? jobs.filter((j) => j.project_id === projectId && j.type === 'forest' && j.status === 'success')
    : []

  // Источник уклонов — только те успешные сессии «Рельефа», где была отмечена
  // «Карта уклонов»: без неё растра уклонов в результатах сессии нет.
  const slopeJobs = projectId
    ? jobs.filter(
        (j) =>
          j.project_id === projectId &&
          j.type === 'relief' &&
          j.status === 'success' &&
          (j.params as ReliefParams).derivatives?.slopes,
      )
    : []

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
        <Button onClick={handleRun} disabled={!deps.ok} title={runTooltip}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {!deps.ok && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          <span>Не хватает: {deps.missing.map((m) => `${m.layer} (вкладка «${m.tab}»)`).join(', ')}</span>
        </div>
      )}

      {/* Шапка модуля: СК, разрешение + источники ЦМД и уклонов */}
      <ModuleHeader
        projectId={projectId ?? ''}
        resolutionPreset={p.output_resolution_preset}
        onResolutionChange={(v: ResolutionPreset) => set('output_resolution_preset', v)}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Источник ЦМД</div>
            <Select
              value={p.cmd_source.system_session_id ?? ''}
              onChange={(e) => set('cmd_source', { ...p.cmd_source, system_session_id: e.target.value || undefined })}
            >
              <option value="">— выбрать сессию —</option>
              {forestJobs.map((j) => (
                <option key={j.id} value={j.session_id ?? j.id}>
                  {j.session_id ?? j.id}
                </option>
              ))}
            </Select>
            {forestJobs.length === 0 && <p className="hint-base mt-1.5">Нет завершённых сессий «Древостоя»</p>}
          </div>

          <div className="rounded-lg border border-slate-200 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Уклоны</div>
            <Select
              value={p.slopes_source.system_session_id ?? ''}
              onChange={(e) => set('slopes_source', { ...p.slopes_source, system_session_id: e.target.value || undefined })}
            >
              <option value="">— выбрать сессию —</option>
              {slopeJobs.map((j) => (
                <option key={j.id} value={j.session_id ?? j.id}>
                  {j.session_id ?? j.id}
                </option>
              ))}
            </Select>
            {slopeJobs.length === 0 && (
              <p className="hint-base mt-1.5">Нет сессий «Рельефа» с рассчитанной картой уклонов</p>
            )}
          </div>
        </div>
      </ModuleHeader>

      {/* Сегментация вод */}
      <Card>
        <CardPad>
          <Accordion title="Сегментация поверхностных вод">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Field
                  label="Порог уверенности модели"
                  tooltip="Порог бинаризации маски вероятности. Значения выше порога → вода, ниже → не вода. Допустимые значения от 0.01 до 1 с шагом 0.01, по умолчанию 0.7."
                >
                  <NumberInput value={p.segment.threshold} step={0.01} min={0.01} max={1} onChange={(v) => set('segment', { ...p.segment, threshold: v })} />
                </Field>
              </div>
            </div>
          </Accordion>
        </CardPad>
      </Card>
    </div>
  )
}