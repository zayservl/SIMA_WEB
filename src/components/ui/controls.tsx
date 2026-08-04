import * as React from 'react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Info } from 'lucide-react'
import { cn } from '@/lib/utils'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} className={cn('input-base', className)} {...props} />
  ),
)
Input.displayName = 'Input'

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn('input-base appearance-none pr-8', className)} {...props}>
      {children}
    </select>
  ),
)
Select.displayName = 'Select'

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn('input-base py-2', className)} {...props} />
  ),
)
Textarea.displayName = 'Textarea'

export function Label({ className, children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn('label-base', className)} {...props}>{children}</label>
  )
}

export function Checkbox({ checked, onChange, label, disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean
}) {
  return (
    <label className={cn('inline-flex items-center gap-2 text-sm text-slate-700', disabled && 'opacity-40 cursor-not-allowed')}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-slate-300 accent-brand-600"
      />
      {label && <span>{label}</span>}
    </label>
  )
}

export function Radio({ checked, onChange, label, disabled }: {
  checked: boolean; onChange: () => void; label: string; disabled?: boolean
}) {
  return (
    <label className={cn('inline-flex items-center gap-2 text-sm text-slate-700', disabled && 'opacity-40 cursor-not-allowed')}>
      <input
        type="radio"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="h-4 w-4 border-slate-300 accent-brand-600"
      />
      <span>{label}</span>
    </label>
  )
}

export function Field({ label, hint, tooltip, children, className }: {
  label: string
  hint?: string
  tooltip?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-center gap-1">
        <Label>{label}</Label>
        {tooltip && <InfoHint text={tooltip} />}
      </div>
      {children}
      {hint && <p className="hint-base">{hint}</p>}
    </div>
  )
}

// NumberInput с буфером строки и валидацией границ.
// - Пустое поле / NaN не схлопывается в 0 молча: подсвечивается красным,
//   предыдущее число сохраняется.
// - Выход за min/max — красная рамка + клэмп на blur.
export function NumberInput({ value, onChange, step, min, max, disabled, className }: {
  value: number
  onChange: (v: number) => void
  step?: number
  min?: number
  max?: number
  disabled?: boolean
  className?: string
}) {
  const [text, setText] = useState(String(value))
  const [invalid, setInvalid] = useState(false)
  const textRef = useRef(text)
  textRef.current = text

  // Синхронизируем буфер с внешним значением, не затирая промежуточные
  // состояния ввода (напр. "12." или "").
  useEffect(() => {
    const parsed = parseFloat(textRef.current)
    if (isNaN(parsed) || parsed !== value) setText(String(value))
  }, [value])

  const evaluate = (raw: string) => {
    setText(raw)
    if (raw === '' || raw === '-' || raw === '.' || raw === '-.') {
      setInvalid(true)
      return // не зовём onChange — сохраняем прошлое значение
    }
    const parsed = parseFloat(raw)
    if (isNaN(parsed)) { setInvalid(true); return }
    let bad = false
    if (min !== undefined && parsed < min) bad = true
    if (max !== undefined && parsed > max) bad = true
    setInvalid(bad)
    onChange(parsed)
  }

  const clampOnBlur = () => {
    const parsed = parseFloat(text)
    if (isNaN(parsed)) { setText(String(value)); setInvalid(false); return }
    let v = parsed
    if (min !== undefined && v < min) v = min
    if (max !== undefined && v > max) v = max
    if (v !== parsed) { setText(String(v)); onChange(v) }
    setInvalid(false)
  }

  return (
    <Input
      type="number"
      value={text}
      step={step}
      min={min}
      max={max}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      onChange={(e) => evaluate(e.target.value)}
      onBlur={clampOnBlur}
      className={cn('w-full', invalid && 'border-red-400 focus:border-red-400 focus:ring-red-100', className)}
    />
  )
}

// Иконка-подсказка с тултипом — единый компонент для всех страниц.
export function InfoHint({ text }: { text: string }) {
  return (
    <Tooltip content={text}>
      <Info className="h-3.5 w-3.5 text-slate-300 hover:text-slate-400" />
    </Tooltip>
  )
}

// Тултип. Всплывающее окно выносится порталом в body и позиционируется
// фиксированно: иначе его режут родители с overflow (аккордеон, таблицы,
// скролл-область main) — тёмный фон обрезается, а текст выходит за него.
// Положение: над триггером, при нехватке места сверху — под ним; по горизонтали
// прижимается к краям окна с отступом 8 px.
export function Tooltip({ content, children }: { content: string; children: React.ReactNode }) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const tipRef = useRef<HTMLSpanElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const trigger = triggerRef.current?.getBoundingClientRect()
      const tip = tipRef.current?.getBoundingClientRect()
      if (!trigger || !tip) return
      const margin = 8
      const gap = 6
      const fitsAbove = trigger.top - tip.height - gap >= margin
      const top = fitsAbove ? trigger.top - tip.height - gap : trigger.bottom + gap
      const centered = trigger.left + trigger.width / 2 - tip.width / 2
      const left = Math.min(Math.max(margin, centered), window.innerWidth - tip.width - margin)
      setPos({ top, left })
    }
    place()
    // Скролл в любом контейнере и ресайз сдвигают триггер — пересчитываем.
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, content])

  const close = () => { setOpen(false); setPos(null) }

  return (
    <>
      <span
        ref={triggerRef}
        className="tooltip-wrap"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={close}
        onFocus={() => setOpen(true)}
        onBlur={close}
      >
        {children}
      </span>
      {open &&
        createPortal(
          <span
            ref={tipRef}
            role="tooltip"
            className="tooltip"
            // До первого замера держим скрытым: иначе виден кадр в углу экрана.
            style={{ transform: `translate(${pos?.left ?? 0}px, ${pos?.top ?? 0}px)`, visibility: pos ? 'visible' : 'hidden' }}
          >
            {content}
          </span>,
          document.body,
        )}
    </>
  )
}