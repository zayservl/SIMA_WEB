import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { totalOutputSize, tempFilesSize, jobLog } from '@/lib/outputs'
import type { Job, JobType, Tile } from '@/api/types'
import {
  Database, Download, FileArchive, HardDrive, FolderTree, ScrollText,
  CheckCircle2, XCircle, Clock, ChevronDown, ChevronRight, Layers,
  SlidersHorizontal,
} from 'lucide-react'

const PARAM_LABELS: Record<string, string> = {
  filter_method: 'Метод фильтрации',
  filter: 'Фильтр',
  spm_min: 'SPM min',
  spm_max: 'SPM max',
  spr_num: 'SPR кол-во',
  spp_min: 'SPP min',
  spp_max: 'SPP max',
  mean_k: 'K среднего',
  mult: 'Множитель',
  smrf: 'SMRF',
  slope: 'Наклон',
  window: 'Окно',
  threshold: 'Порог',
  scalar: 'Скаляр',
  cut_smrf: 'Резать SMRF',
  elm: 'ELM',
  outlier: 'Выбросы',
  smoothing: 'Сглаживание',
  enabled: 'Включено',
  sigma: 'Сигма',
  order: 'Порядок',
  smoothing_preset: 'Пресет сглаживания',
  output_resolution_preset: 'Пресет разрешения',
  dsm: 'ЦММ',
  output_type: 'Агрегация точек',
  interpolate: 'Интерполяция',
  fill_holes: 'Заполнение пустот',
  max_search_distance: 'Радиус поиска, пикс',
  derivatives: 'Производные',
  slopes: 'Уклоны',
  slopes_res: 'Разрешение уклонов',
  aspect: 'Экспозиция',
  aspect_res: 'Разрешение экспозиции',
  tpi: 'TPI',
  tpi_radii: 'Радиусы TPI',
  interpolation: 'Интерполяция',
  inter_amp: 'Амплитуда интерп.',
  edge_extrapolation_m: 'Экстраполяция края, м',
  heights: 'Высоты',
  source: 'Источник',
  step: 'Шаг',
  vectors: 'Векторы',
  horizontals: 'Горизонтали',
  tin: 'TIN',
  target_crs: 'Целевая СК',
  deterministic: 'Детерминизм',
  seed: 'Seed',
  cmd: 'CMD',
  threshold_surface: 'Порог поверхность',
  threshold_shrub: 'Порог кустарник',
  channels: 'Каналы',
  chm: 'CHM',
  median_window: 'Окно медианы',
  detection: 'Обнаружение',
  method: 'Метод',
  vegetation_state: 'Состояние растительности',
  stats: 'Статистика',
  percentiles: 'Перцентили',
  vci_step: 'Шаг VCI',
  metrics: 'Метрики',
  logging_category: 'Категория перечёта',
  algorithm: 'Алгоритм',
  features: 'Признаки',
  thresholds: 'Пороги',
  hght: 'Высота',
  dist_far: 'Дист. дальняя',
  dist_near: 'Дист. ближняя',
  diam: 'Диаметр',
  table: 'Таблица',
  rows: 'Строки',
  category: 'Категория',
  density: 'Плотность',
  dsm_source: 'Источник ЦММ',
  derivatives_source: 'Источник производных',
  segment: 'Сегментация',
  dem_source: 'Источник ЦМР',
  slopes_source: 'Источник уклонов',
  mode: 'Определение параметров',
  kind: 'Тип',
  system_session_id: 'ID системной сессии',
  upload_path: 'Путь загрузки',
}

// Значения-перечисления в человекочитаемом виде.
const PARAM_VALUE_LABELS: Record<string, string> = {
  ai: 'ИИ',
  algorithmic: 'алгоритмически',
}

type ParamValue = string | number | boolean | null | undefined | ParamValue[] | { [key: string]: ParamValue }

function renderParamsValue(value: ParamValue, depth = 0): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-slate-400">—</span>
  }
  if (typeof value === 'boolean') {
    return <span className={value ? 'text-emerald-600' : 'text-slate-400'}>{value ? 'Да' : 'Нет'}</span>
  }
  if (Array.isArray(value)) {
    return <span className="text-slate-700">{value.join(', ')}</span>
  }
  if (typeof value === 'object') {
    return (
      <div className={depth > 0 ? 'ml-4 space-y-1' : 'space-y-1'}>
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="shrink-0 text-slate-500">{PARAM_LABELS[k] ?? k}:</span>
            <span className="text-slate-800">{renderParamsValue(v, depth + 1)}</span>
          </div>
        ))}
      </div>
    )
  }
  return <span className="text-slate-700">{PARAM_VALUE_LABELS[String(value)] ?? String(value)}</span>
}

const typeLabel: Record<JobType, string> = { relief: 'Рельеф', forest: 'Древостой', water: 'Вода' }
const statusLabel: Record<Job['status'], string> = {
  queued: 'в очереди', running: 'выполняется', success: 'готово', failed: 'ошибка', cancelled: 'отменена',
}
const statusVariant: Record<Job['status'], 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  queued: 'neutral', running: 'warning', success: 'success', failed: 'danger', cancelled: 'neutral',
}
const kindColor: Record<string, string> = {
  raster: 'text-sky-600',
  vector: 'text-emerald-600',
  'point-cloud': 'text-violet-600',
}

export default function Data() {
  const { projectId } = useParams()
  const jobs = useProjectStore((s) => (projectId ? s.jobs.filter((j) => j.project_id === projectId) : s.jobs))
  const [toast, setToast] = useState<string | null>(null)

  const fireArchive = (what: string) => setToast(`Готовится архив: ${what} (демо-заглушка)`)

  if (jobs.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-slate-400">
        <Database className="mb-3 h-12 w-12" />
        <p className="text-sm">Нет данных. Запустите обработку — выходные файлы появятся здесь.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Данные и результаты</h1>
        <p className="mt-1 text-sm text-slate-500">Выходные файлы по тайлам, каталоги сессий, архивы и лог</p>
      </div>

      {toast && (
        <div className="flex items-center justify-between rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs text-brand-700">
          <span>{toast}</span>
          <button onClick={() => setToast(null)} className="text-brand-500 hover:text-brand-700">✕</button>
        </div>
      )}

      <div className="space-y-4">
        {jobs.map((job) => (
          <SessionCard key={job.id} job={job} onArchive={fireArchive} />
        ))}
      </div>
    </div>
  )
}

function SessionCard({ job, onArchive }: { job: Job; onArchive: (what: string) => void }) {
  const [tab, setTab] = useState<'files' | 'log' | 'params'>('files')
  const [openTileId, setOpenTileId] = useState<string | null>(null)
  const project = useProjectStore.getState().projects.find((p) => p.id === job.project_id)
  const seed = project?.scene.seed
  const deterministic = project?.scene.deterministic ?? true

  const doneTiles = job.tiles.filter((t) => t.status === 'done' && t.output_files && t.output_files.length > 0)
  const totalMb = totalOutputSize(job)
  const tempMb = tempFilesSize(job)

  return (
    <Card>
      <CardPad>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <FolderTree className="h-5 w-5 text-slate-400" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{typeLabel[job.type]}</span>
                <Badge variant={statusVariant[job.status]}>{statusLabel[job.status]}</Badge>
                {job.session_id && <span className="font-mono text-[10px] text-slate-400">сессия {job.session_id}</span>}
                <span className={cn('text-[10px]', deterministic ? 'text-emerald-600' : 'text-slate-400')}>
                  {deterministic ? 'детерминизм' : 'недетерминировано'}{seed != null ? ` · seed ${seed}` : ''}
                </span>
              </div>
              {job.output_dir ? (
                <div className="mt-0.5 break-all font-mono text-[11px] text-slate-500">{job.output_dir}</div>
              ) : (
                <div className="mt-0.5 text-[11px] text-slate-400">каталог сессии будет создан при запуске</div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onArchive(`${typeLabel[job.type]} · сессия ${job.session_id}`)} disabled={doneTiles.length === 0}>
              <FileArchive className="h-3.5 w-3.5" /> Архив задачи
            </Button>
          </div>
        </div>

        {/* Сводка объёмов */}
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <VolumeTile icon={<HardDrive className="h-4 w-4 text-slate-400" />} label="Выходные данные" value={`${totalMb.toFixed(1)} МБ`} sub={`${doneTiles.length} тайл(ов)`} />
          <VolumeTile icon={<Layers className="h-4 w-4 text-amber-500" />} label="Промежуточные" value={`${tempMb.toFixed(1)} МБ`} sub="очищаются после тайла" />
          <VolumeTile icon={<CheckCircle2 className="h-4 w-4 text-emerald-500" />} label="Готово тайлов" value={`${job.tiles_done}/${job.tiles_total}`} sub={`${job.tiles_failed} с ошибкой`} />
        </div>

        {/* Табы: Файлы / Лог / Параметры */}
        <div className="mt-4 flex items-center gap-1 border-b border-slate-100">
          {(['files', 'log', 'params'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors',
                tab === t ? 'border-brand-500 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-700'
              )}
            >
              {t === 'files' && <><Database className="h-3.5 w-3.5" /> Файлы по тайлам</>}
              {t === 'log' && <><ScrollText className="h-3.5 w-3.5" /> Лог по шагам</>}
              {t === 'params' && <><SlidersHorizontal className="h-3.5 w-3.5" /> Параметры</>}
            </button>
          ))}
        </div>

        {tab === 'files' ? (
          <div className="mt-3 space-y-1">
            {doneTiles.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400">Нет завершённых тайлов с выходными данными</div>
            ) : (
              doneTiles.map((t) => (
                <TileFilesRow key={t.id} tile={t} open={openTileId === t.id} onToggle={() => setOpenTileId(openTileId === t.id ? null : t.id)} onArchive={() => onArchive(`${t.name} (${typeLabel[job.type]})`)} />
              ))
            )}
          </div>
        ) : tab === 'log' ? (
          <LogView job={job} />
        ) : (
          <div className="mt-3 space-y-1 font-mono text-[11px]">
            {renderParamsValue(job.params as unknown as ParamValue)}
          </div>
        )}
      </CardPad>
    </Card>
  )
}

function TileFilesRow({ tile, open, onToggle, onArchive }: { tile: Tile; open: boolean; onToggle: () => void; onArchive: () => void }) {
  const size = (tile.output_files || []).reduce((a, f) => a + f.size_mb, 0)
  return (
    <div className="rounded-lg border border-slate-100">
      <button onClick={onToggle} className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-slate-50">
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3.5 w-3.5 text-slate-400" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-400" />}
          <span className="font-mono text-xs">{tile.name}</span>
          {tile.retry_of && <Badge variant="neutral">повтор</Badge>}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-500">
          <span>{tile.output_files?.length} файл(ов)</span>
          <span className="font-mono">{size.toFixed(1)} МБ</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-3 py-2">
          <div className="mb-2 break-all font-mono text-[10px] text-slate-400">{tile.output_dir}</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[10px] text-slate-400">
                <th className="py-1 pr-3 font-medium">Файл</th>
                <th className="py-1 pr-3 font-medium">Тип</th>
                <th className="py-1 pr-3 font-medium">Формат</th>
                <th className="py-1 pr-3 font-medium">Размер</th>
                <th className="py-1 text-right font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {(tile.output_files || []).map((f) => (
                <tr key={f.id} className="border-t border-slate-50">
                  <td className="py-1.5 pr-3 font-mono text-[11px] text-slate-700">{f.name}</td>
                  <td className={cn('py-1.5 pr-3', kindColor[f.kind])}>{f.kind}</td>
                  <td className="py-1.5 pr-3 text-slate-500">{f.format}</td>
                  <td className="py-1.5 pr-3 font-mono text-slate-500">{f.size_mb} МБ</td>
                  <td className="py-1.5 text-right">
                    <button
                      onClick={(e) => { e.stopPropagation(); onArchive() }}
                      title="Скачать файл"
                      className="inline-flex items-center gap-1 rounded border border-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600 hover:bg-slate-100"
                    >
                      <Download className="h-3 w-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex justify-end">
            <Button variant="outline" size="sm" onClick={onArchive}>
              <FileArchive className="h-3 w-3" /> Архив тайла
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function LogView({ job }: { job: Job }) {
  const lines = jobLog(job)
  if (lines.length === 0) {
    return <div className="py-6 text-center text-xs text-slate-400">Лог пока пуст — запустите обработку</div>
  }
  return (
    <div className="mt-3 max-h-80 overflow-auto rounded-lg border border-slate-100 bg-slate-50/40 p-3">
      <div className="space-y-1 font-mono text-[11px]">
        {lines.map((l, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="shrink-0 text-slate-400">{l.ts ? new Date(l.ts).toLocaleTimeString('ru-RU') : '--:--:--'}</span>
            <span className="shrink-0 text-slate-500">{l.tile}</span>
            <span className="shrink-0 text-slate-700">{l.step}</span>
            {l.status === 'done' && <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-500" />}
            {l.status === 'failed' && <XCircle className="h-3 w-3 shrink-0 text-red-500" />}
            {l.status === 'skipped' && <Clock className="h-3 w-3 shrink-0 text-slate-400" />}
            {l.duration_ms != null && <span className="shrink-0 text-slate-400">({(l.duration_ms / 1000).toFixed(1)} с)</span>}
            {l.message && <span className="text-red-600">{l.message}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

function VolumeTile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-3">
      <div className="flex items-center gap-2 text-xs text-slate-500">{icon}{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-slate-800">{value}</div>
      <div className="text-[10px] text-slate-400">{sub}</div>
    </div>
  )
}