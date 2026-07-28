// Общая шапка страницы модуля (Relief/Forest/Water) — СК, сглаживание,
// разрешение выходного файла, слот для тултипов методов и доп. контента.
// Повторяющийся блок вынесен в один компонент, чтобы страницы модулей
// сосредоточились на специфичных параметрах.

import type { ReactNode } from 'react'
import { Globe, AlertTriangle } from 'lucide-react'
import type { SmoothingPreset, ResolutionPreset } from '@/api/types'
import { useProjectStore } from '@/store/projectStore'
import { Select, Field, InfoHint } from '@/components/ui/controls'
import { Card, CardPad } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { METHOD_TOOLTIPS } from '@/lib/methodTooltips'

interface ModuleHeaderProps {
  projectId: string
  smoothingPreset: SmoothingPreset
  resolutionPreset: ResolutionPreset
  onSmoothingChange: (v: SmoothingPreset) => void
  onResolutionChange: (v: ResolutionPreset) => void
  methodTooltips?: ReactNode
  children?: ReactNode
}

const SMOOTHING_OPTIONS: { value: SmoothingPreset; label: string }[] = [
  { value: 'none', label: 'Нет' },
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

export function ModuleHeader({
  projectId,
  smoothingPreset,
  resolutionPreset,
  onSmoothingChange,
  onResolutionChange,
  methodTooltips,
  children,
}: ModuleHeaderProps) {
  const projects = useProjectStore((s) => s.projects)
  const project = projects.find((p) => p.id === projectId)
  const crs = project?.scene.target_crs ?? ''
  const crsEmpty = !crs

  // Предупреждение: разрешение мельче исходного (демо-логика: всё не-native).
  const resolutionWarn = resolutionPreset !== 'native'

  return (
    <Card>
      <CardPad>
        <div className="flex flex-wrap items-end gap-4">
          {/* СК (readOnly) */}
          <div className="min-w-[220px] flex-1">
            <div className="mb-1.5 flex items-center gap-1">
              <Globe className="h-3.5 w-3.5 text-slate-400" />
              <span className="label-base">Система координат</span>
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
          <Field label="Сглаживание" tooltip={METHOD_TOOLTIPS.smoothing} className="w-40">
            <Select value={smoothingPreset} onChange={(e) => onSmoothingChange(e.target.value as SmoothingPreset)}>
              {SMOOTHING_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>

          {/* Разрешение выходного файла */}
          <Field label="Разрешение выходного файла" tooltip={METHOD_TOOLTIPS.resolution} className="w-44">
            <Select value={resolutionPreset} onChange={(e) => onResolutionChange(e.target.value as ResolutionPreset)}>
              {RESOLUTION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
            {resolutionWarn && (
              <div className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-600">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>Разрешение мельче исходного — возможно ухудшение качества</span>
              </div>
            )}
          </Field>
        </div>

        {/* Слот тултипов методов */}
        {methodTooltips && <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-slate-500">{methodTooltips}</div>}

        {/* Слот доп. контента (переключатели источника и т.п.) */}
        {children && <div className="mt-3">{children}</div>}
      </CardPad>
    </Card>
  )
}

export default ModuleHeader