import { cn } from '@/lib/utils'

type BadgeVariant = 'neutral' | 'success' | 'warning' | 'danger' | 'info'
const styles: Record<BadgeVariant, string> = {
  neutral: 'bg-slate-100 text-slate-600',
  success: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/60',
  warning: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200/60',
  danger: 'bg-red-50 text-red-700 ring-1 ring-red-200/60',
  info: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200/60',
}

export function Badge({ variant = 'neutral', children, className }: {
  variant?: BadgeVariant; children: React.ReactNode; className?: string
}) {
  return (
    <span className={cn('pill', styles[variant], className)}>
      {children}
    </span>
  )
}