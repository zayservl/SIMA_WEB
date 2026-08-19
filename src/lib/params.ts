// Сравнение текущих параметров модуля с эталонными. Умолчания воспроизводят
// конфигурацию тестовых ноутбуков, поэтому «чем текущая настройка отличается
// от эталонной» — вопрос, который возникает после первого же эксперимента.

export interface ParamChange {
  /** Путь до поля: «dsm.fill_passes». */
  path: string
  from: unknown
  to: unknown
}

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

/** Список полей, отличающихся от эталона. Массивы сравниваются целиком. */
export function diffParams(current: unknown, base: unknown, prefix = ''): ParamChange[] {
  if (isPlainObject(current) && isPlainObject(base)) {
    return Object.keys(current).flatMap((k) =>
      diffParams(current[k], base[k], prefix ? `${prefix}.${k}` : k),
    )
  }
  const same = Array.isArray(current) || Array.isArray(base)
    ? JSON.stringify(current) === JSON.stringify(base)
    : current === base
  return same ? [] : [{ path: prefix, from: base, to: current }]
}

/** Значение параметра в виде, пригодном для строки отчёта. */
export function formatValue(v: unknown): string {
  if (typeof v === 'boolean') return v ? 'да' : 'нет'
  if (Array.isArray(v)) return v.join(', ')
  if (v === '' || v === undefined || v === null) return '—'
  return String(v)
}
