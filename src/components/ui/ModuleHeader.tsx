// Общая шапка страницы модуля (Relief/Forest/Water) — СК, сглаживание,
// разрешение выходного файла, слот для тултипов методов и доп. контента.
// Повторяющийся блок вынесен в один компонент, чтобы страницы модулей
// сосредоточились на специфичных параметрах.

import { useState, type ReactNode } from 'react'
import { Globe, AlertTriangle, RotateCcw, ChevronDown, ChevronRight } from 'lucide-react'
import { formatValue, type ParamChange } from '@/lib/params'
import { Button } from '@/components/ui/button'
import type { SmoothingPreset, ResolutionPreset } from '@/api/types'
import { useProjectStore } from '@/store/projectStore'
import { Select, Field, InfoHint, NumberInput } from '@/components/ui/controls'
import { Card, CardPad } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { METHOD_TOOLTIPS } from '@/lib/methodTooltips'

/** Экспертные параметры гауссова фильтра (backend: gauss_smooth). */
export interface CustomSmoothing {
  sigma: number
  order: number
  window: number
}

/**
 * Пресет сглаживания → параметры гауссова фильтра. Общий для «Рельефа» и
 * «Древостоя». Окно входит в пресет наравне с сигмой: у сильного сглаживания
 * ядро шире, и в relief_demo эксперт задаёт именно пару 2.0 / 5.
 */
export const SMOOTHING_BY_PRESET: Record<Exclude<SmoothingPreset, 'custom' | 'off'>, { sigma: number; window: number }> = {
  light: { sigma: 0.5, window: 3 },
  medium: { sigma: 1.0, window: 3 },
  strong: { sigma: 2.0, window: 5 },
}

interface ModuleHeaderProps {
  projectId: string
  /** Сглаживание показывается, только если модуль передал пресет и обработчик (в «Воде» параметра нет). */
  smoothingPreset?: SmoothingPreset
  /** Разрешение показывается, только если модуль передал пресет и обработчик (в «Воде» параметра нет). */
  resolutionPreset?: ResolutionPreset
  onSmoothingChange?: (v: SmoothingPreset) => void
  onResolutionChange?: (v: ResolutionPreset) => void
  /**
   * Пользовательские настройки. Опция «Пользовательские настройки» появляется
   * в выпадающем списке только у модулей, которые передали значения и обработчик.
   */
  customSmoothing?: CustomSmoothing
  onCustomSmoothingChange?: (patch: Partial<CustomSmoothing>) => void
  customResolutionM?: number
  onCustomResolutionChange?: (v: number) => void
  methodTooltips?: ReactNode
  /**
   * Режим «Все параметры». В основном режиме на экране остаётся то, что
   * задаётся в типовой работе; экспертная настройка скрыта, но в один клик.
   */
  expert?: boolean
  onExpertChange?: (v: boolean) => void
  /** Отличия текущей настройки от эталонной (умолчаний). */
  changes?: ParamChange[]
  onReset?: () => void
  children?: ReactNode
}

const SMOOTHING_OPTIONS: { value: SmoothingPreset; label: string }[] = [
  { value: 'off', label: 'Без сглаживания' },
  { value: 'light', label: 'Слабое' },
  { value: 'medium', label: 'Среднее' },
  { value: 'strong', label: 'Сильное' },
]

const RESOLUTION_OPTIONS: { value: ResolutionPreset; label: string }[] = [
  { value: 'native', label: 'Исходное' },
  { value: '0.1m', label: '0.1 м' },
  { value: '0.25m', label: '0.25 м' },
  { value: '0.5m', label: '0.5 м' },
  { value: '1m', label: '1 м' },
  { value: '2m', label: '2 м' },
]

/** Пресет → метры на пиксель. 'native' и 'custom' задаются иначе. */
const RESOLUTION_METRES: Partial<Record<ResolutionPreset, number>> = {
  '0.1m': 0.1, '0.25m': 0.25, '0.5m': 0.5, '1m': 1, '2m': 2,
}

const CUSTOM_SMOOTHING_LABEL = 'Пользовательское'
const CUSTOM_RESOLUTION_LABEL = 'Пользовательское'

export function ModuleHeader({
  projectId,
  smoothingPreset,
  resolutionPreset,
  onSmoothingChange,
  onResolutionChange,
  customSmoothing,
  onCustomSmoothingChange,
  customResolutionM,
  onCustomResolutionChange,
  methodTooltips,
  expert,
  onExpertChange,
  changes,
  onReset,
  children,
}: ModuleHeaderProps) {
  const [changesOpen, setChangesOpen] = useState(false)
  const projects = useProjectStore((s) => s.projects)
  const project = projects.find((p) => p.id === projectId)
  const crs = project?.scene.target_crs ?? ''
  const crsEmpty = !crs

  // Предупреждение имеет смысл только против фактического разрешения съёмки:
  // просить ячейку мельче исходной — значит рисовать детали, которых в данных
  // нет. Разрешение читается из оценки материалов; без неё сравнивать не с чем.
  const nativeResM = useProjectStore((s) => (projectId ? s.assessment[projectId]?.afs?.resolution_m : undefined))
  const selectedResM = resolutionPreset
    ? resolutionPreset === 'custom' ? customResolutionM : RESOLUTION_METRES[resolutionPreset]
    : undefined
  const resolutionWarn =
    selectedResM !== undefined && nativeResM !== undefined && selectedResM < nativeResM
  const smoothingCustomizable = !!customSmoothing && !!onCustomSmoothingChange
  const resolutionCustomizable = customResolutionM !== undefined && !!onCustomResolutionChange

  return (
    <Card>
      <CardPad>
        {/* items-start: у «Пользовательского» под списком появляется поле ввода,
            и выравнивание по нижнему краю уводило бы соседние блоки вниз. */}
        <div className="flex flex-wrap items-start gap-4">
          {/* СК (readOnly) */}
          <div className="min-w-[220px] flex-1">
            <div className="mb-1.5 flex items-center gap-1">
              <Globe className="h-3.5 w-3.5 text-slate-400" />
              <span className="label-base">Система координат</span>
              <InfoHint text="Система координат наследуется из входящих файлов" />
            </div>
            <div
              className={cn(
                'rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm',
                crsEmpty ? 'text-amber-600' : 'text-slate-700',
              )}
            >
              {crsEmpty ? 'не определена, загрузите файлы' : crs}
            </div>
          </div>

          {/* Сглаживание */}
          {smoothingPreset && onSmoothingChange && (
            <Field label="Сглаживание" tooltip={METHOD_TOOLTIPS.smoothing} className="w-48">
              <Select value={smoothingPreset} onChange={(e) => onSmoothingChange(e.target.value as SmoothingPreset)}>
                {SMOOTHING_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
                {smoothingCustomizable && <option value="custom">{CUSTOM_SMOOTHING_LABEL}</option>}
              </Select>
            </Field>
          )}

          {/* Разрешение выходного файла */}
          {resolutionPreset && onResolutionChange && (
            <Field label="Разрешение расчёта" tooltip={METHOD_TOOLTIPS.resolution} className="w-56">
              <Select value={resolutionPreset} onChange={(e) => onResolutionChange(e.target.value as ResolutionPreset)}>
                {RESOLUTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
                {resolutionCustomizable && <option value="custom">{CUSTOM_RESOLUTION_LABEL}</option>}
              </Select>
              {resolutionPreset === 'custom' && resolutionCustomizable ? (
                <div className="mt-1.5">
                  <NumberInput
                    value={customResolutionM!}
                    step={0.05}
                    min={0.01}
                    onChange={onCustomResolutionChange!}
                  />
                  <p className="hint-base mt-1">м/пиксель</p>
                  {resolutionWarn && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-600">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>Мельче исходного ({nativeResM} м) — детализация не вырастет</span>
                    </div>
                  )}
                </div>
              ) : (
                resolutionWarn && (
                  <div className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-600">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    <span>Мельче исходного ({nativeResM} м) — детализация не вырастет</span>
                  </div>
                )
              )}
            </Field>
          )}
        </div>

        {/* Экспертные параметры сглаживания — только в режиме «Пользовательские настройки» */}
        {smoothingPreset === 'custom' && smoothingCustomizable && (
          <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3">
            <div className="mb-2 flex items-center gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Параметры гауссова фильтра</span>
              <InfoHint text="Параметры гауссова фильтра: сигма умножается на пространственное разрешение растра, порядок — производная гауссианы (0 — обычное сглаживание), окно — размер ядра в пикселях." />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Сигма" tooltip="Коэффициент умножается на пространственное разрешение растра. Чем больше — тем сильнее сглаживание.">
                <NumberInput
                  value={customSmoothing!.sigma} step={0.1} min={0}
                  onChange={(v) => onCustomSmoothingChange!({ sigma: v })}
                />
              </Field>
              <Field label="Порядок" tooltip="Порядок производной гауссова фильтра. 0 — обычное сглаживание.">
                <NumberInput
                  value={customSmoothing!.order} min={0}
                  onChange={(v) => onCustomSmoothingChange!({ order: v })}
                />
              </Field>
              <Field label="Окно, пикс" tooltip="Размер окна фильтра в пикселях — определяет усечение ядра (truncate).">
                <NumberInput
                  value={customSmoothing!.window} min={1}
                  onChange={(v) => onCustomSmoothingChange!({ window: v })}
                />
              </Field>
            </div>
          </div>
        )}

        {/* Режим отображения параметров и отличия от эталонной настройки */}
        {(onExpertChange || changes) && (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3">
            {onExpertChange && (
              <div className="inline-flex rounded-lg bg-slate-100 p-0.5">
                {([false, true] as const).map((v) => (
                  <button
                    key={String(v)}
                    type="button"
                    onClick={() => onExpertChange(v)}
                    className={cn(
                      'rounded-md px-3 py-1 text-xs transition-colors',
                      expert === v ? 'bg-white font-medium text-slate-700 shadow-sm' : 'text-slate-500 hover:text-slate-700',
                    )}
                  >
                    {v ? 'Все параметры' : 'Основные'}
                  </button>
                ))}
              </div>
            )}
            {changes && (
              changes.length === 0 ? (
                <span className="text-xs text-slate-400">настройка эталонная</span>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setChangesOpen((v) => !v)}
                    className="inline-flex items-center gap-1 text-xs font-medium text-amber-600 hover:text-amber-700"
                  >
                    {changesOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                    изменено параметров: {changes.length}
                  </button>
                  {onReset && (
                    <Button variant="outline" size="sm" onClick={onReset} title="Вернуть параметры модуля к эталонным — тем, на которых снималась точность">
                      <RotateCcw className="h-3 w-3" /> Откатить настройки
                    </Button>
                  )}
                </>
              )
            )}
          </div>
        )}
        {changes && changesOpen && changes.length > 0 && (
          <div className="mt-2 max-h-40 overflow-y-auto rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
            <ul className="space-y-0.5">
              {changes.map((c) => (
                <li key={c.path}>
                  <span className="font-mono">{c.path}</span>: {formatValue(c.from)} → <b>{formatValue(c.to)}</b>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Слот тултипов методов */}
        {methodTooltips && <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-slate-500">{methodTooltips}</div>}

        {/* Слот доп. контента (переключатели источника и т.п.) */}
        {children && <div className="mt-3">{children}</div>}
      </CardPad>
    </Card>
  )
}

export default ModuleHeader