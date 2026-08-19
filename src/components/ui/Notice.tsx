// Плашка-уведомление. Об одном и том же — чего не хватает для расчёта —
// говорили три места разной вёрсткой и разным тоном. Единая форма: заголовок
// «чего нет», под ним строки «почему», в конце — «где взять».

import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export type NoticeVariant = 'info' | 'warning' | 'danger' | 'success'

const STYLE: Record<NoticeVariant, string> = {
  info: 'bg-slate-50 text-slate-500',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-red-50 text-red-700',
  success: 'bg-emerald-50 text-emerald-700',
}

const ICON = {
  info: Info,
  warning: AlertTriangle,
  danger: XCircle,
  success: CheckCircle2,
}

export function Notice({ variant = 'info', title, action, className, children }: {
  variant?: NoticeVariant
  /** Первая строка — что именно не так. Выделяется, когда есть подробности. */
  title?: ReactNode
  /** Последняя строка — куда идти. */
  action?: ReactNode
  className?: string
  children?: ReactNode
}) {
  const Icon = ICON[variant]
  return (
    <div className={cn('flex items-start gap-2 rounded-lg p-3 text-xs', STYLE[variant], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 space-y-1">
        {title && <div className={children || action ? 'font-medium' : undefined}>{title}</div>}
        {children}
        {action && <div>{action}</div>}
      </div>
    </div>
  )
}
