import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { artifactsFor, tileDir } from '@/lib/outputs'
import { jobOutcome } from '@/lib/jobs'
import type { Job, JobType, Tile, TileStatus, StepStatus } from '@/api/types'
import {
  CheckCircle2, XCircle, Loader2, Clock, ChevronDown, ChevronRight, Circle,
  Search, SkipForward, Square, SlidersHorizontal, Ban, AlertTriangle, Pencil, Check, X,
} from 'lucide-react'

const typeLabel: Record<JobType, string> = { relief: 'Рельеф', forest: 'Древостой', water: 'Вода' }

const failReasons = [
  'PDAL: пустой файл', 'Нет класса Ground', 'CUDA OOM', 'Повреждённый файл', 'Нет данных в экстенте',
  'Несовпадение СК', 'Ошибка интерполяции', 'Слишком мало точек',
]

const now = () => new Date().toISOString()
const durMs = (a?: string, b?: string) => (a && b ? Date.parse(b) - Date.parse(a) : undefined)

// Один шаг симуляции: продвигаем активный тайл на один шаг вперёд.
function advanceJob(cur: Job): Partial<Job> | null {
  const tiles: Tile[] = cur.tiles.map((t) => ({ ...t, steps: t.steps.map((s) => ({ ...s })) }))

  let activeIdx = tiles.findIndex((t) => t.status === 'running')
  if (activeIdx === -1) {
    activeIdx = tiles.findIndex((t) => t.status === 'queued')
    if (activeIdx === -1) return null // нечего двигать
    const t = tiles[activeIdx]
    t.status = 'running'
    t.started_at = now()
    const first = t.steps[0]
    first.status = 'running'
    first.started_at = now()
    t.current_step = first.name
  } else {
    const t = tiles[activeIdx]
    const stepIdx = t.steps.findIndex((s) => s.status === 'running')
    if (stepIdx === -1) return null
    const step = t.steps[stepIdx]

    // Доля сбоев подобрана так, чтобы на прогоне было видно и разбор ошибок,
    // и осмысленный результат: при 0.12 на шаг падало большинство тайлов.
    if (Math.random() < 0.03) {
      step.status = 'failed'
      step.finished_at = now()
      step.duration_ms = durMs(step.started_at, step.finished_at)
      step.message = failReasons[Math.floor(Math.random() * failReasons.length)]
      t.status = 'failed'
      t.current_step = step.name
      t.finished_at = step.finished_at
      t.duration_ms = durMs(t.started_at, t.finished_at)
      t.reason = step.message
    } else {
      step.status = 'done'
      step.finished_at = now()
      step.duration_ms = durMs(step.started_at, step.finished_at)
      if (stepIdx + 1 < t.steps.length) {
        const next = t.steps[stepIdx + 1]
        next.status = 'running'
        next.started_at = now()
        t.current_step = next.name
      } else {
        t.status = 'done'
        t.finished_at = now()
        t.duration_ms = durMs(t.started_at, t.finished_at)
        t.current_step = undefined
        // Сохранение данных после обработки тайла (Блок Г): фиксируем путь и
        // список выходных артефактов. Повторный запуск создаст новый tile.id →
        // новую вложенную папку, старые данные не затираются.
        t.output_dir = tileDir(cur, t)
        t.output_files = artifactsFor(cur, t)
      }
    }
  }

  const done = tiles.filter((t) => t.status === 'done').length
  const failed = tiles.filter((t) => t.status === 'failed').length
  const skipped = tiles.filter((t) => t.status === 'skipped').length
  const processed = done + failed + skipped
  const progress = Math.round((processed / cur.tiles_total) * 100)
  const failed_tiles = tiles
    .filter((t) => t.status === 'failed')
    .map((t) => ({ name: t.name, reason: t.reason || '' }))

  const patch: Partial<Job> = {
    tiles, tiles_done: done, tiles_failed: failed, tiles_skipped: skipped, progress, failed_tiles,
  }
  if (processed >= cur.tiles_total) {
    patch.status = 'success'
    patch.progress = 100
    patch.finished_at = now()
  }
  return patch
}

// SSE-симуляция: один шаг каждые ~400 мс. При подключении реального бэкенда
// заменяется на EventSource/WebSocket — остальная UI-логика не меняется.
// Один стабильный интервал читает стор императивно (не зависит от меняющихся
// ссылок `jobs`, иначе пересоздание таймеров на каждом тике приводило бы к остановке).
function useJobSimulation(updateJob: (id: string, patch: Partial<Job>) => void) {
  useEffect(() => {
    const interval = window.setInterval(() => {
      const state = useProjectStore.getState()
      state.jobs.forEach((job) => {
        if (job.status === 'queued') {
          updateJob(job.id, {
            status: 'running',
            started_at: now(),
            output_dir: job.output_dir ?? `results/${job.project_id}/${job.type}/session-${job.session_id ?? 'unknown'}`,
          })
          return
        }
        if (job.status !== 'running') return
        const patch = advanceJob(job)
        if (patch) updateJob(job.id, patch)
      })
    }, 400)
    return () => clearInterval(interval)
  }, [updateJob])
}

type FilterKey = 'all' | 'queued' | 'running' | 'failed' | 'done' | 'skipped'

const filterChips: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'queued', label: 'В очереди' },
  { key: 'running', label: 'В процессе' },
  { key: 'failed', label: 'Ошибка' },
  { key: 'done', label: 'Готово' },
  { key: 'skipped', label: 'Пропущен' },
]

export default function Tasks() {
  const { projectId } = useParams()
  const navigate = useNavigate()
  const jobs = useProjectStore((s) => (projectId ? s.jobs.filter((j) => j.project_id === projectId) : s.jobs))
  const updateJob = useProjectStore((s) => s.updateJob)
  useJobSimulation(updateJob)

  if (jobs.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-slate-400">
        <Clock className="mb-3 h-12 w-12" />
        <p className="text-sm">Нет задач. Запустите обработку из раздела «Рельеф», «Древостой» или «Вода».</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Очередь задач</h1>
        <p className="mt-1 text-sm text-slate-500">Просмотр и управление задачами обработки</p>
      </div>

      <div className="space-y-4">
        {jobs.map((job) => {
          const project = useProjectStore.getState().projects.find((p) => p.id === job.project_id)
          const seed = project?.scene.seed
          const deterministic = project?.scene.deterministic ?? true
          const recomputeSrc = job.recompute_of
            ? useProjectStore.getState().jobs.find((j) => j.id === job.recompute_of)
            : undefined
          return (
            <JobCard
              key={job.id}
              job={job}
              seed={seed}
              deterministic={deterministic}
              recomputeSrc={recomputeSrc}
              onRetry={() =>
                updateJob(job.id, {
                  status: 'queued', progress: 0, tiles_done: 0, tiles_failed: 0, tiles_skipped: 0,
                  failed_tiles: [], finished_at: undefined,
                  tiles: job.tiles.map((t) => ({
                    ...t,
                    status: 'queued' as TileStatus,
                    started_at: undefined, finished_at: undefined, duration_ms: undefined,
                    current_step: undefined, reason: undefined,
                    output_dir: undefined, output_files: undefined,
                    steps: t.steps.map((s) => ({ ...s, status: 'pending' as StepStatus, started_at: undefined, finished_at: undefined, duration_ms: undefined, message: undefined })),
                  })),
                })
              }
              onRecompute={() =>
                projectId && navigate(`/projects/${projectId}/${job.type}`, { state: { retryParams: job.params } })
              }
              onRecomputeFailed={() =>
                projectId && navigate(`/projects/${projectId}/${job.type}`, { state: { retryParams: job.params, recomputeFailedOf: job.id } })
              }
            />
          )
        })}
      </div>
    </div>
  )
}

// Имя расчёта: показ и правка на месте. Пустое имя не сохраняется — задача
// без имени неотличима от соседних в списке.
function JobName({ job }: { job: Job }) {
  const updateJob = useProjectStore((s) => s.updateJob)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(job.name)

  const commit = () => {
    const next = draft.trim()
    if (next) updateJob(job.id, { name: next })
    else setDraft(job.name)
    setEditing(false)
  }
  const cancel = () => { setDraft(job.name); setEditing(false) }

  if (!editing) {
    return (
      <span className="group inline-flex items-center gap-1.5">
        <span className="text-sm font-semibold">{job.name}</span>
        <button
          onClick={() => { setDraft(job.name); setEditing(true) }}
          title="Переименовать расчёт"
          className="text-slate-400 transition-colors hover:text-slate-600"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1">
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') cancel() }}
        onBlur={commit}
        className="h-7 w-56 rounded-md border border-slate-200 px-2 text-sm font-semibold focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
      />
      {/* onMouseDown, а не onClick: blur поля срабатывает раньше клика и закрыл бы правку */}
      <button onMouseDown={(e) => { e.preventDefault(); commit() }} title="Сохранить" className="text-emerald-600 hover:text-emerald-700">
        <Check className="h-3.5 w-3.5" />
      </button>
      <button onMouseDown={(e) => { e.preventDefault(); cancel() }} title="Отменить" className="text-slate-400 hover:text-slate-600">
        <X className="h-3.5 w-3.5" />
      </button>
    </span>
  )
}

function JobCard({ job, seed, deterministic, recomputeSrc, onRetry, onRecompute, onRecomputeFailed }: {
  job: Job
  seed?: number
  deterministic: boolean
  recomputeSrc?: Job
  onRetry: () => void
  onRecompute: () => void
  onRecomputeFailed: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [query, setQuery] = useState('')
  const [openTileId, setOpenTileId] = useState<string | null>(null)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const stopTile = useProjectStore((s) => s.stopTile)
  const cancelJob = useProjectStore((s) => s.cancelJob)
  const cancellable = job.status === 'queued' || job.status === 'running'
  const outcome = jobOutcome(job)

  const icon = job.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin text-amber-500" />
    : job.status === 'success' ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    : job.status === 'failed' ? <XCircle className="h-4 w-4 text-red-500" />
    : <Clock className="h-4 w-4 text-slate-400" />

  const counts = {
    done: job.tiles.filter((t) => t.status === 'done').length,
    running: job.tiles.filter((t) => t.status === 'running').length,
    failed: job.tiles.filter((t) => t.status === 'failed').length,
    queued: job.tiles.filter((t) => t.status === 'queued').length,
    skipped: job.tiles.filter((t) => t.status === 'skipped').length,
  }

  const filtered = job.tiles.filter((t) => {
    if (filter !== 'all' && t.status !== filter) return false
    if (query && !t.name.toLowerCase().includes(query.toLowerCase())) return false
    return true
  })

  return (
    <Card>
      <CardPad>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5">{icon}</div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <JobName job={job} />
                <Badge variant="neutral">{typeLabel[job.type]}</Badge>
                <Badge variant={outcome.variant}>{outcome.label}</Badge>
              </div>
              <div className="text-xs text-slate-500">
                {job.started_at && `старт: ${new Date(job.started_at).toLocaleTimeString('ru-RU')}`}
                {job.finished_at && ` · финиш: ${new Date(job.finished_at).toLocaleTimeString('ru-RU')}`}
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-slate-400">
                <span className={deterministic ? 'text-emerald-600' : 'text-slate-400'}>
                  {deterministic ? 'детерминизм' : 'недетерминировано'}
                </span>
                {seed != null && <span className="font-mono">· seed {seed}</span>}
                {job.session_id && <span className="font-mono">· сессия {job.session_id}</span>}
              </div>
              {recomputeSrc && (
                <div className="mt-0.5 text-[11px] text-slate-400">
                  пересчёт от «{recomputeSrc.name}» · сессия {recomputeSrc.session_id}
                </div>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <div className="text-right text-xs">
              <div className="text-slate-500">
                готово {job.tiles_done} из {job.tiles_total}
                {job.status === 'running' && ` · ${job.progress}%`}
              </div>
              {job.tiles_failed > 0 && <div className="text-amber-600">{job.tiles_failed} с ошибкой</div>}
              {job.tiles_skipped > 0 && <div className="text-slate-400">{job.tiles_skipped} пропущено</div>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {cancellable && (
                <Button variant="outline" size="sm" onClick={() => setConfirmCancel(true)} title="Отменить расчёт: посчитанные результаты сессии будут удалены">
                  <Ban className="h-3 w-3" /> Отменить расчёт
                </Button>
              )}
              {job.tiles_failed > 0 && (
                <Button variant="outline" size="sm" onClick={onRecomputeFailed} title="Пересчитать упавшие тайлы с новыми параметрами (новая сессия)">
                  <SlidersHorizontal className="h-3 w-3" /> Пересчитать упавшие
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={onRecompute} title="Пересчитать с новыми параметрами (новая сессия)">
                <SlidersHorizontal className="h-3 w-3" /> Пересчитать с новыми параметрами
              </Button>
            </div>
          </div>
        </div>

        {/* Подтверждение отмены: действие необратимо — уже посчитанные тайлы теряются */}
        {confirmCancel && cancellable && (
          <div className="mt-3 flex flex-wrap items-center gap-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              Отменить расчёт? Результаты сессии {job.session_id}, посчитанные к этому моменту
              ({job.tiles_done} из {job.tiles_total} тайлов), будут удалены.
            </span>
            <div className="ml-auto flex gap-2">
              <Button variant="danger" size="sm" onClick={() => { cancelJob(job.id); setConfirmCancel(false) }}>
                <Ban className="h-3 w-3" /> Отменить и удалить
              </Button>
              <Button variant="outline" size="sm" onClick={() => setConfirmCancel(false)}>
                Продолжить расчёт
              </Button>
            </div>
          </div>
        )}

        {job.status === 'cancelled' && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
            <Ban className="h-4 w-4 shrink-0" />
            Расчёт отменён, посчитанные результаты удалены. Запустите заново через «Пересчитать с новыми параметрами».
          </div>
        )}

        {/* Прогресс-бар */}
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={cn('h-full transition-all', job.tiles_failed > 0 ? 'bg-amber-400' : 'bg-brand-500')}
            style={{ width: `${job.progress}%` }}
          />
        </div>

        {/* Сводка по статусам тайлов */}
        <div className="mt-3 flex flex-wrap gap-3 text-xs">
          <span className="inline-flex items-center gap-1 text-emerald-600"><CheckCircle2 className="h-3.5 w-3.5" /> Готово: {counts.done}</span>
          <span className="inline-flex items-center gap-1 text-amber-600"><Loader2 className="h-3.5 w-3.5" /> В процессе: {counts.running}</span>
          <span className="inline-flex items-center gap-1 text-red-600"><XCircle className="h-3.5 w-3.5" /> Ошибка: {counts.failed}</span>
          <span className="inline-flex items-center gap-1 text-slate-400"><Circle className="h-3.5 w-3.5" /> В очереди: {counts.queued}</span>
          {counts.skipped > 0 && (
            <span className="inline-flex items-center gap-1 text-slate-400"><SkipForward className="h-3.5 w-3.5" /> Пропущено: {counts.skipped}</span>
          )}
        </div>

        {/* Кнопка раскрытия */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 flex items-center gap-1 text-xs font-medium text-brand-700 hover:text-brand-800"
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {expanded ? 'Скрыть тайлы' : 'Показать все тайлы'}
        </button>

        {/* Фильтры + таблица тайлов */}
        {expanded && (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex flex-wrap gap-1.5">
                {filterChips.map((c) => (
                  <button
                    key={c.key}
                    onClick={() => setFilter(c.key)}
                    className={cn(
                      'rounded-md px-2.5 py-1 text-xs transition-colors',
                      filter === c.key ? 'bg-brand-50 text-brand-700 font-medium' : 'text-slate-500 hover:bg-slate-50'
                    )}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
              <div className="relative ml-auto">
                <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Поиск по имени…"
                  className="h-8 w-56 rounded-lg border border-slate-200 bg-white pl-7 pr-3 text-xs placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                />
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-100">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50 text-left text-xs text-slate-500">
                    <th className="py-2 px-3">Тайл</th>
                    <th className="py-2 px-3">Статус</th>
                    <th className="py-2 px-3">Шаг</th>
                    <th className="py-2 px-3">Время</th>
                    <th className="py-2 px-3 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t) => {
                    const open = openTileId === t.id
                    return (
                      <TileRow
                        key={t.id}
                        tile={t}
                        open={open}
                        onToggle={() => setOpenTileId(open ? null : t.id)}
                        onStop={() => stopTile(job.id, t.id)}
                      />
                    )
                  })}
                  {filtered.length === 0 && (
                    <tr><td colSpan={5} className="py-6 text-center text-xs text-slate-400">Нет тайлов по фильтру</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {job.failed_tiles.length > 0 && !expanded && (
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
            <XCircle className="h-4 w-4 shrink-0" />
            Остановлено {job.failed_tiles.length} тайл(ов). Раскройте для подробностей.
          </div>
        )}
      </CardPad>
    </Card>
  )
}

function TileRow({ tile, open, onToggle, onStop }: {
  tile: Tile
  open: boolean
  onToggle: () => void
  onStop: () => void
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-slate-50 last:border-0 hover:bg-slate-50/60"
      >
        <td className="py-2 px-3">
          <div className="flex items-center gap-2">
            {open ? <ChevronDown className="h-3 w-3 text-slate-400" /> : <ChevronRight className="h-3 w-3 text-slate-400" />}
            <span className="font-mono text-xs">{tile.name}</span>
            {tile.retry_of && <Badge variant="neutral">повтор</Badge>}
          </div>
        </td>
        <td className="py-2 px-3"><TileStatusBadge status={tile.status} /></td>
        <td className="py-2 px-3 text-xs text-slate-600">
          {tile.status === 'running' && tile.current_step
            ? <span className="inline-flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin text-amber-500" />{tile.current_step}</span>
            : tile.status === 'failed' && tile.current_step
              ? <span className="text-red-600">{tile.current_step}</span>
              : tile.status === 'done' ? <span className="text-slate-400">все шаги выполнены</span> : '—'}
        </td>
        <td className="py-2 px-3 text-xs text-slate-500">
          {tile.duration_ms != null ? `${(tile.duration_ms / 1000).toFixed(1)} с` : tile.started_at ? `с ${new Date(tile.started_at).toLocaleTimeString('ru-RU')}` : '—'}
        </td>
        <td className="py-2 px-3 text-right" onClick={(e) => e.stopPropagation()}>
          <div className="flex justify-end gap-1.5">
            {tile.status === 'running' && (
              <button
                onClick={onStop}
                title="Остановить тайл"
                className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-100"
              >
                <Square className="h-3 w-3" /> Стоп
              </button>
            )}
          </div>
        </td>
      </tr>
      {open && (
        <tr className="bg-slate-50/40">
          <td colSpan={5} className="px-3 py-3">
            <TileStepsTimeline tile={tile} />
          </td>
        </tr>
      )}
    </>
  )
}

function TileStepsTimeline({ tile }: { tile: Tile }) {
  return (
    <div className="space-y-1.5 pl-5">
      <div className="mb-2 flex items-center gap-3 text-xs text-slate-500">
        {tile.started_at && <span>старт: {new Date(tile.started_at).toLocaleTimeString('ru-RU')}</span>}
        {tile.finished_at && <span>финиш: {new Date(tile.finished_at).toLocaleTimeString('ru-RU')}</span>}
        {tile.duration_ms != null && <span>· {(tile.duration_ms / 1000).toFixed(1)} с</span>}
        {tile.reason && <span className="text-red-600">· {tile.reason}</span>}
      </div>
      {tile.status === 'done' && tile.output_dir && (
        <div className="mb-2 rounded-md border border-slate-200 bg-white p-2 text-xs">
          <div className="text-slate-500">Сохранено в:</div>
          <div className="mt-0.5 break-all font-mono text-[11px] text-slate-700">{tile.output_dir}</div>
          {tile.output_files && tile.output_files.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {tile.output_files.map((f) => (
                <span key={f.id} className="inline-flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600" title={f.path}>
                  <span className="font-mono">{f.name}</span>
                  <span className="text-slate-400">{f.format}</span>
                  <span className="text-slate-400">{f.size_mb} МБ</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <ol className="space-y-1">
        {tile.steps.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-xs">
            <StepIcon status={s.status} />
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className={cn(s.status === 'failed' ? 'text-red-600' : 'text-slate-700')}>{s.name}</span>
                <span className="font-mono text-[10px] text-slate-400">
                  {s.duration_ms != null ? `${(s.duration_ms / 1000).toFixed(1)} с`
                    : s.started_at ? `с ${new Date(s.started_at).toLocaleTimeString('ru-RU')}`
                    : ''}
                </span>
              </div>
              {s.message && <div className="text-[11px] text-slate-500">{s.message}</div>}
            </div>
          </li>
        ))}
      </ol>
      {/* Шаги-плейсхолдеры, если у типа нет шагов (не должно случаться) */}
      {tile.steps.length === 0 && <div className="text-xs text-slate-400">Шаги отсутствуют</div>}
    </div>
  )
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === 'done') return <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
  if (status === 'running') return <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-amber-500" />
  if (status === 'failed') return <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
  if (status === 'skipped') return <SkipForward className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
  return <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-300" />
}

function TileStatusBadge({ status }: { status: TileStatus }) {
  if (status === 'done') return <Badge variant="success">Готово</Badge>
  if (status === 'running') return <Badge variant="warning">В процессе</Badge>
  if (status === 'failed') return <Badge variant="danger">Ошибка</Badge>
  if (status === 'skipped') return <Badge variant="neutral">Пропущен</Badge>
  return <Badge variant="neutral">В очереди</Badge>
}