import { useMemo, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useProjectStore, defaultWaterParams } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Accordion } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { NumberInput, Field } from '@/components/ui/controls'
import { ModuleHeader } from '@/components/ui/ModuleHeader'
import { RunSetup } from '@/components/ui/RunSetup'
import { Play, AlertTriangle } from 'lucide-react'
import type { WaterParams, Job } from '@/api/types'
import { defaultJobName, moduleRunTiles, availableNames } from '@/lib/jobs'
import { generateTilesFromNames } from '@/lib/tiles'
import { checkDependencies } from '@/lib/dependencies'

export default function Water() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const addJob = useProjectStore((s) => s.addJob)
  const jobs = useProjectStore((s) => s.jobs)
  // Повтор старой сессии: из сохранённых параметров берём только те, что
  // остались в контракте (ЦМР и разрешение из модуля убраны).
  const [p, setP] = useState<WaterParams>(() => {
    const retry = (location.state as { retryParams?: WaterParams } | null)?.retryParams
    return { segment: { ...defaultWaterParams.segment, ...retry?.segment } }
  })
  const [jobName, setJobName] = useState(() => defaultJobName('water', jobs, projectId ?? ''))
  const inputTiles = useProjectStore((s) => (projectId ? s.inputTiles[projectId] : undefined))
  const runTiles = useMemo(() => moduleRunTiles('water', inputTiles ?? []), [inputTiles])
  // По умолчанию на расчёт идут все доступные тайлы.
  const [selectedTiles, setSelectedTiles] = useState<string[]>(() => availableNames(runTiles))
  const set = <K extends keyof WaterParams>(k: K, v: WaterParams[K]) => setP((s) => ({ ...s, [k]: v }))

  const handleRun = () => {
    if (!projectId) return
    const job: Job = {
      id: 'j-' + Math.random().toString(36).slice(2, 9),
      name: jobName.trim() || defaultJobName('water', jobs, projectId),
      project_id: projectId, type: 'water', status: 'queued', progress: 0,
      tiles_total: selectedTiles.length, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0, failed_tiles: [],
      tiles: generateTilesFromNames('water', selectedTiles),
      started_at: new Date().toISOString(), params: p,
    }
    addJob(job)
    navigate(`/projects/${projectId}/tasks`)
  }

  const isRetry = !!(location.state as { retryParams?: unknown } | null)?.retryParams

  const deps = checkDependencies(projectId || '', 'water')
  const runTooltip = deps.ok
    ? selectedTiles.length === 0 ? 'Не выбрано ни одного тайла для расчёта' : undefined
    : 'Не хватает: ' + deps.missing.map((m) => m.layer).join(', ') + '. Загрузите данные на вкладке: ' + deps.missing.map((m) => m.tab).join(', ')

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
        <Button onClick={handleRun} disabled={!deps.ok || selectedTiles.length === 0} title={runTooltip}><Play className="h-4 w-4" /> Запустить</Button>
      </div>

      {!deps.ok && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-amber-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          <span>Не хватает: {deps.missing.map((m) => `${m.layer} (вкладка «${m.tab}»)`).join(', ')}</span>
        </div>
      )}

      {/* Шапка модуля: СК + единственный источник — АФС */}
      <ModuleHeader projectId={projectId ?? ''}>
        <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-500">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Источник АФС</div>
          Каталог АФС проекта из «Загрузки данных» — по нему строится маска воды. ЦМР, ЦМД и
          производные рельефа на этом этапе не используются.
        </div>
      </ModuleHeader>

      <RunSetup
        name={jobName}
        onNameChange={setJobName}
        tiles={runTiles}
        selected={selectedTiles}
        onSelectedChange={setSelectedTiles}
      />

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