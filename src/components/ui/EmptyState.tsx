// Пустой экран — лучшее место для маршрута: вместо констатации «данных нет»
// показываем шаги, которые к ним ведут, и отмечаем уже пройденные.

import { Link } from 'react-router-dom'
import { CheckCircle2, Circle, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface RouteStep {
  label: string
  to: string
  /** Шаг пройден — отмечаем галочкой и не зовём на него. */
  done: boolean
  hint?: string
}

export function EmptyState({ icon: Icon, title, steps }: {
  icon: LucideIcon
  title: string
  steps: RouteStep[]
}) {
  // Звать имеет смысл на первый непройденный шаг.
  const nextIndex = steps.findIndex((s) => !s.done)

  return (
    <div className="mx-auto flex max-w-md flex-col items-center py-16 text-center">
      <Icon className="mb-3 h-10 w-10 text-slate-300" />
      <p className="text-sm font-medium text-slate-600">{title}</p>
      <ol className="mt-5 w-full space-y-2 text-left">
        {steps.map((s, i) => (
          <li
            key={s.to}
            className={cn(
              'flex items-start gap-2.5 rounded-lg border px-3 py-2.5',
              i === nextIndex ? 'border-brand-200 bg-brand-50/50' : 'border-slate-200',
            )}
          >
            {s.done
              ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
              : <Circle className={cn('mt-0.5 h-4 w-4 shrink-0', i === nextIndex ? 'text-brand-500' : 'text-slate-300')} />}
            <div className="min-w-0 flex-1">
              <Link
                to={s.to}
                className={cn(
                  'text-sm',
                  i === nextIndex ? 'font-medium text-brand-700 hover:text-brand-800' : 'text-slate-600 hover:text-slate-800',
                )}
              >
                {s.label}
              </Link>
              {s.hint && <p className="hint-base mt-0.5">{s.hint}</p>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
