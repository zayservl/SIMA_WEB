// Русские числительные: «1 тайл», «2 тайла», «5 тайлов». Формы «N файл(ов)»
// в интерфейсе, показываемом заказчику, читаются как след разработки.

/** Выбрать форму слова по числу: [один, два, пять]. */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100
  const tail = abs % 10
  if (abs > 10 && abs < 20) return forms[2]
  if (tail > 1 && tail < 5) return forms[1]
  if (tail === 1) return forms[0]
  return forms[2]
}

/** Число вместе со словом: «3 тайла». */
export function withPlural(n: number, forms: [string, string, string]): string {
  return `${n} ${plural(n, forms)}`
}

export const TILES: [string, string, string] = ['тайл', 'тайла', 'тайлов']
/** Родительный падеж: «для 1 тайла», «для 5 тайлов». */
export const TILES_GEN: [string, string, string] = ['тайла', 'тайлов', 'тайлов']
export const FILES: [string, string, string] = ['файл', 'файла', 'файлов']
