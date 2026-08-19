// Общий блок «Запуск расчёта» для страниц Рельеф/Древостой/Вода: имя расчёта
// и выбор тайлов, отправляемых на расчёт. Одинаков для всех модулей, поэтому
// вынесен из страниц в один компонент.

import { useState } from 'react'
import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Field, Input } from '@/components/ui/controls'
import { cn } from '@/lib/utils'
import { AlertTriangle, Grid3x3, Search, ListChecks } from 'lucide-react'
import { availableNames, groupByReason, type RunTile } from '@/lib/jobs'
import { withPlural, TILES, TILES_GEN } from '@/lib/plural'

// Перечисление имён полезно, пока их можно охватить взглядом. Два десятка
// имён в строку — шум: там достаточно числа, сами тайлы видны в списке выше.
const NAMES_LIMIT = 10

function namesLabel(names: string[], total: number): string {
  if (names.length === total) return 'все тайлы проекта'
  if (names.length <= NAMES_LIMIT) return names.join(', ')
  return `${names.slice(0, NAMES_LIMIT).join(', ')} и ещё ${withPlural(names.length - NAMES_LIMIT, TILES)}`
}

type TileFilter = 'all' | 'available' | 'unavailable'

const FILTERS: { key: TileFilter; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'available', label: 'Доступные' },
  { key: 'unavailable', label: 'Недоступные' },
]

export function RunSetup({ name, onNameChange, tiles, selected, onSelectedChange, inheritedFrom, summary }: {
  name: string
  onNameChange: (v: string) => void
  tiles: RunTile[]
  selected: string[]
  onSelectedChange: (v: string[]) => void
  /** Имя расчёта, из которого унаследован набор тайлов. */
  inheritedFrom?: string
  /** Строки сводки «что пойдёт в расчёт» — состав задаёт сам модуль. */
  summary?: string[]
}) {
  const [filter, setFilter] = useState<TileFilter>('all')
  const [query, setQuery] = useState('')

  const available = availableNames(tiles)
  const unavailable = tiles.filter((t) => !t.available)
  const allSelected = available.length > 0 && selected.length === available.length

  const visible = tiles.filter((t) => {
    if (filter === 'available' && !t.available) return false
    if (filter === 'unavailable' && t.available) return false
    return !query || t.name.toLowerCase().includes(query.toLowerCase())
  })

  const toggle = (tileName: string) =>
    onSelectedChange(
      selected.includes(tileName) ? selected.filter((n) => n !== tileName) : [...selected, tileName],
    )

  const byReason = groupByReason(unavailable)

  return (
    <Card>
      <CardPad>
        <CardHeader title="Запуск расчёта" subtitle="Название сессии и набор тайлов" />
        <div className="space-y-4">
          <Field
            label="Название расчёта"
            hint="Как расчёт будет назван в очереди задач и в менеджере данных. Имя можно изменить позже."
            className="sm:max-w-md"
          >
            <Input value={name} onChange={(e) => onNameChange(e.target.value)} />
          </Field>

          <div>
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span className="label-base inline-flex items-center gap-1.5">
                <Grid3x3 className="h-3.5 w-3.5 text-slate-400" />
                Тайлы на расчёт
              </span>
              <span className="text-xs text-slate-500">
                выбрано {selected.length} из {available.length}
              </span>
              <button
                type="button"
                disabled={available.length === 0}
                onClick={() => onSelectedChange(allSelected ? [] : available)}
                className="text-xs font-medium text-brand-700 hover:text-brand-800 disabled:text-slate-300"
              >
                {allSelected ? 'Снять все' : 'Выбрать все'}
              </button>
              {inheritedFrom && (
                <span className="text-xs text-slate-400">
                  набор унаследован из «{inheritedFrom}»
                </span>
              )}
            </div>

            {tiles.length > 0 && (
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <div className="flex flex-wrap gap-1.5">
                  {FILTERS.map((f) => (
                    <button
                      key={f.key}
                      type="button"
                      onClick={() => setFilter(f.key)}
                      className={cn(
                        'rounded-md px-2.5 py-1 text-xs transition-colors',
                        filter === f.key ? 'bg-brand-50 font-medium text-brand-700' : 'text-slate-500 hover:bg-slate-50',
                      )}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
                <div className="relative ml-auto">
                  <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Поиск по имени…"
                    className="h-8 w-48 rounded-lg border border-slate-200 bg-white pl-7 pr-3 text-xs placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
                  />
                </div>
              </div>
            )}

            {tiles.length === 0 ? (
              <p className="hint-base">
                Каталог тайлов пуст. Загрузите материалы и нажмите «Оценить материалы» на вкладке
                «Загрузка данных».
              </p>
            ) : (
              <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 p-2">
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
                  {visible.length === 0 && (
                    <p className="hint-base col-span-full py-2">Под фильтр ничего не подошло</p>
                  )}
                  {visible.map((t) => (
                    <label
                      key={t.name}
                      title={t.reason}
                      className={cn(
                        'inline-flex items-center gap-2 rounded px-1.5 py-1 font-mono text-xs',
                        t.available ? 'text-slate-700 hover:bg-slate-50' : 'cursor-not-allowed text-slate-400',
                      )}
                    >
                      <input
                        type="checkbox"
                        disabled={!t.available}
                        checked={t.available && selected.includes(t.name)}
                        onChange={() => toggle(t.name)}
                        className="h-3.5 w-3.5 rounded border-slate-300 accent-brand-600"
                      />
                      <span className="truncate">{t.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {unavailable.length > 0 && (
              <div className="mt-2 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-1">
                  <div>
                    Данных недостаточно для {withPlural(unavailable.length, TILES_GEN)} — они недоступны к расчёту:
                  </div>
                  {byReason.map(([reason, names]) => (
                    <div key={reason}>
                      <span className="font-medium">{reason}</span> — {namesLabel(names, tiles.length)}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {available.length > 0 && selected.length === 0 && (
              <p className="mt-2 text-xs text-amber-600">
                Не выбрано ни одного тайла — расчёт запустить нельзя.
              </p>
            )}
          </div>

          {/* Что реально пойдёт в расчёт: иначе это приходится собирать,
              пролистывая все аккордеоны параметров. */}
          {summary && summary.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
              <div className="mb-1.5 flex items-center gap-1.5">
                <ListChecks className="h-3.5 w-3.5 text-slate-400" />
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Пойдёт в расчёт
                </span>
              </div>
              <ul className="space-y-0.5 text-xs text-slate-600">
                {summary.map((line) => <li key={line}>{line}</li>)}
                <li>Тайлов: {selected.length}</li>
              </ul>
            </div>
          )}
        </div>
      </CardPad>
    </Card>
  )
}
