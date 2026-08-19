// Общий блок «Запуск расчёта» для страниц Рельеф/Древостой/Вода: имя расчёта
// и выбор тайлов, отправляемых на расчёт. Одинаков для всех модулей, поэтому
// вынесен из страниц в один компонент.

import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Field, Input } from '@/components/ui/controls'
import { cn } from '@/lib/utils'
import { AlertTriangle, Grid3x3 } from 'lucide-react'
import { availableNames, groupByReason, type RunTile } from '@/lib/jobs'

export function RunSetup({ name, onNameChange, tiles, selected, onSelectedChange }: {
  name: string
  onNameChange: (v: string) => void
  tiles: RunTile[]
  selected: string[]
  onSelectedChange: (v: string[]) => void
}) {
  const available = availableNames(tiles)
  const unavailable = tiles.filter((t) => !t.available)
  const allSelected = available.length > 0 && selected.length === available.length

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
            </div>

            {tiles.length === 0 ? (
              <p className="hint-base">
                Каталог тайлов пуст. Загрузите материалы и нажмите «Оценить материалы» на вкладке
                «Загрузка данных».
              </p>
            ) : (
              <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-200 p-2">
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
                  {tiles.map((t) => (
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
                    Данных недостаточно для {unavailable.length} тайлов — они недоступны к расчёту:
                  </div>
                  {byReason.map(([reason, names]) => (
                    <div key={reason}>
                      <span className="font-medium">{reason}</span> —{' '}
                      {/* Причина, накрывшая весь каталог, поимённого списка не проясняет. */}
                      {names.length === tiles.length ? 'все тайлы проекта' : names.join(', ')}
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
        </div>
      </CardPad>
    </Card>
  )
}
