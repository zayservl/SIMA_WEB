import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Field, InfoHint, NumberInput } from '@/components/ui/controls'
import { Badge } from '@/components/ui/badge'
import { FolderOpen, AlertTriangle, CheckCircle2, Layers, Grid3x3 } from 'lucide-react'
import type { MaterialAssessment } from '@/api/types'
import {
  generateMockInputTiles, CLASS_LABELS, TARGET_CRS,
  inputMode, originOffsetM, formatOrigin, DEFAULT_ORIGIN_TOLERANCE_M,
  type InputTile, type InputMode,
} from '@/lib/inputTiles'

// Требования к именам входящих файлов и правило спаривания. Единый текст для
// тултипов у обоих каталогов.
const NAMING_TOOLTIP =
  'Файлы АФС и ВЛС спариваются по числовому индексу в имени: 000100.tif + pt000100.las → tile_001. ' +
  'Индекс — шесть цифр с ведущими нулями, регистр расширения не важен. ' +
  'Файлы, для которых не нашлась пара, показываются как неполные и пропускаются при пакетной обработке. ' +
  'Пробелы, кириллица и точки внутри имени не допускаются.'

// Расхождение СК внутри пары не блокирует расчёт: целевая СК проекта — это СК
// АФС, и материалы с другой СК приводятся к ней безусловно. Единственное, что
// снимает тайл с обработки, — отсутствие одного из файлов пары.
type PairStatus = 'ok' | 'reproject' | 'incomplete' | 'vls_only' | 'afs_only'

function pairStatus(t: InputTile, mode: InputMode): PairStatus {
  // Отсутствие целого каталога — это режим работы, а не ошибка валидации.
  if (mode === 'vls-only') return t.vls ? 'vls_only' : 'incomplete'
  if (mode === 'afs-only') return t.afs ? 'afs_only' : 'incomplete'
  if (!t.afs || !t.vls) return 'incomplete'
  return t.afs.crs === t.vls.crs ? 'ok' : 'reproject'
}

const pairLabel: Record<PairStatus, string> = {
  ok: 'СК совпадают',
  reproject: 'СК разнятся → приведение',
  incomplete: 'Неполная пара',
  vls_only: 'Только ВЛС',
  afs_only: 'Только АФС',
}
const pairVariant: Record<PairStatus, 'success' | 'warning' | 'danger' | 'neutral'> = {
  ok: 'success', reproject: 'warning', incomplete: 'neutral',
  vls_only: 'warning', afs_only: 'warning',
}

// Система высот сводки: значение выводится, только если оно одинаково во всех
// файлах. Разнобой или пропуск хотя бы в одном файле — «не указана».
function commonVerticalCrs(values: (string | undefined)[]): string | undefined {
  const first = values[0]
  return first && values.every((v) => v === first) ? first : undefined
}

// Сводный отчёт для совместимости со стором (MaterialAssessment) — агрегат по тайлам.
function aggregate(tiles: InputTile[]): MaterialAssessment {
  const afsTiles = tiles.filter((t) => t.afs)
  const vlsTiles = tiles.filter((t) => t.vls)
  return {
    afs: afsTiles.length ? {
      crs: afsTiles[0].afs!.crs,
      vertical_crs: commonVerticalCrs(afsTiles.map((t) => t.afs!.vertical_crs)),
      extent_area_km2: +afsTiles.reduce((a, t) => a + t.area_km2, 0).toFixed(2),
      resolution_m: Math.min(...afsTiles.map((t) => t.afs!.resolution_m)),
      ofp_scale: '1:1400',
      tiles_total: afsTiles.length, tiles_ok: afsTiles.length, tiles_failed: 0, failed_tiles: [],
    } : null,
    vls: vlsTiles.length ? {
      crs: vlsTiles[0].vls!.crs,
      vertical_crs: commonVerticalCrs(vlsTiles.map((t) => t.vls!.vertical_crs)),
      extent_area_km2: +vlsTiles.reduce((a, t) => a + t.area_km2, 0).toFixed(2),
      density_pts_m2: Math.round(vlsTiles.reduce((a, t) => a + t.vls!.density_pts_m2, 0) / vlsTiles.length),
      tlo_scale: '1:500',
      tlo_height_range_m: [
        Math.min(...vlsTiles.map((t) => t.vls!.height_range_m[0])),
        Math.max(...vlsTiles.map((t) => t.vls!.height_range_m[1])),
      ],
      tiles_total: vlsTiles.length, tiles_ok: vlsTiles.length, tiles_failed: 0, failed_tiles: [],
    } : null,
  }
}

// Строка сводки метаданных: значение отдельно для АФС и для ВЛС.
// «—» — параметр к этому типу материалов не применяется.
function MetaRow({ label, tooltip, afs, vls }: {
  label: string
  tooltip?: string
  afs: React.ReactNode
  vls: React.ReactNode
}) {
  return (
    <tr className="border-b border-slate-100 last:border-0">
      <td className="py-2 pr-4 text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          {label}
          {tooltip && <InfoHint text={tooltip} />}
        </span>
      </td>
      <td className="py-2 pr-4 text-slate-700">{afs}</td>
      <td className="py-2 text-slate-700">{vls}</td>
    </tr>
  )
}

const NO_VALUE = <span className="text-slate-400">—</span>
const UNKNOWN = <span className="text-amber-600">не указана</span>

export default function Upload() {
  const { projectId } = useParams()
  const setAssessment = useProjectStore((s) => s.setAssessment)
  const setInputTiles = useProjectStore((s) => s.setInputTiles)
  const updateScene = useProjectStore((s) => s.updateScene)
  const projects = useProjectStore((s) => s.projects)
  const project = projects.find((p) => p.id === projectId)

  const [afsDir, setAfsDir] = useState(project?.scene.afs_dir || '')
  const [vlsDir, setVlsDir] = useState(project?.scene.vls_dir || '')
  const storedTiles = useProjectStore((s) => (projectId ? s.inputTiles[projectId] : undefined))
  const [tiles, setTiles] = useState<InputTile[]>(() => storedTiles ?? [])
  const [assessed, setAssessed] = useState(() => !!storedTiles?.length)
  const [detectedCrs, setDetectedCrs] = useState<string | null>(
    () => storedTiles?.find((t) => t.afs)?.afs?.crs ?? storedTiles?.find((t) => t.vls)?.vls?.crs ?? null,
  )
  const [originTolM, setOriginTolM] = useState(DEFAULT_ORIGIN_TOLERANCE_M)
  const [mode, setMode] = useState<InputMode>(() => (storedTiles?.length ? inputMode(storedTiles) : 'pair'))

  // Целевая СК = СК АФС (при режиме «только ВЛС» — СК ВЛС): её считывает
  // «Оценить материалы», вручную она не задаётся.
  const targetCrs = project?.scene.target_crs || TARGET_CRS

  const handleAssess = () => {
    if (!projectId) return
    // Каталог, который не указали, задаёт режим работы: без АФС считаем только
    // по ВЛС, без ВЛС доступна только «Вода».
    const nextMode: InputMode = !afsDir ? 'vls-only' : !vlsDir ? 'afs-only' : 'pair'
    setMode(nextMode)
    const generated = generateMockInputTiles(nextMode)
    setTiles(generated)
    setInputTiles(projectId, generated)
    setAssessment(projectId, aggregate(generated))

    // Целевая СК проекта — СК АФС; без АФС берём СК ВЛС.
    const afsCrs = generated.find((t) => t.afs)?.afs?.crs ?? null
    const vlsCrs = generated.find((t) => t.vls)?.vls?.crs ?? null
    const detected = afsCrs ?? vlsCrs
    setDetectedCrs(detected)

    if (detected && projectId) {
      updateScene(projectId, { target_crs: detected })
    }

    setAssessed(true)
  }

  const statuses = tiles.map((t) => pairStatus(t, mode))
  const hasIncomplete = statuses.includes('incomplete')
  // Тайлы, у которых СК ВЛС отличается от целевой — их приводим и называем поимённо.
  const reprojectTiles = tiles.filter((t, i) => statuses[i] === 'reproject')
  // Пары с совпадающей СК, но разъехавшейся геопривязкой: сверяем нижний левый
  // угол тайла. Расчёт не блокируется — решение за пользователем.
  const shiftedTiles = tiles
    .map((t) => ({ tile: t, offset: originOffsetM(t) }))
    .filter((r): r is { tile: InputTile; offset: number } => r.offset !== null && r.offset > originTolM)
  const canProceed = !hasIncomplete

  // Сводка метаданных исходных материалов по обоим типам съёмки.
  const report = tiles.length ? aggregate(tiles) : null

  // Файлы ВЛС с готовой классификацией земли (класс 2 по ASPRS).
  const vlsCount = tiles.filter((t) => t.vls).length
  const classifiedCount = tiles.filter((t) => t.vls?.classes.includes(2)).length

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1>Загрузка данных</h1>
        <p className="mt-1 text-sm text-slate-500">Каталоги АФС и ВЛС</p>
      </div>

      <Card>
        <CardPad>
          <CardHeader title="Исходные каталоги" subtitle="Целевая СК и детерминизм настраиваются в «Параметрах проекта»" />
          <div className="space-y-4">
            <div className="flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
              <Grid3x3 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              <div>
                Разбиение съёмки на тайлы выполняется вне СИМА-web. Система принимает уже нарезанные
                файлы и спаривает их по именам.
              </div>
            </div>
            <Field label="Каталог АФС (.tif, .tiff — GeoTIFF/BigTIFF)" tooltip={NAMING_TOOLTIP}>
              <div className="flex gap-2">
                <FolderOpen className="mt-2 h-4 w-4 shrink-0 text-slate-400" />
                <Input
                  value={afsDir}
                  onChange={(e) => { setAfsDir(e.target.value); setAssessed(false) }}
                  placeholder="/data/afs"
                />
              </div>
            </Field>
            <Field
              label="Каталог ВЛС (.las — LAS 1.2)"
              tooltip={NAMING_TOOLTIP + ' Принимаются как сырые облака, так и файлы с готовой классификацией ASPRS.'}
            >
              <div className="flex gap-2">
                <FolderOpen className="mt-2 h-4 w-4 shrink-0 text-slate-400" />
                <Input
                  value={vlsDir}
                  onChange={(e) => { setVlsDir(e.target.value); setAssessed(false) }}
                  placeholder="/data/vls"
                />
              </div>
            </Field>
            {!afsDir && vlsDir && (
              <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  Каталог АФС не указан — проект пойдёт в режиме «только ВЛС»: «Рельеф» и «Древостой»
                  без детекции крон. «Вода» будет недоступна.
                </div>
              </div>
            )}
            {afsDir && !vlsDir && (
              <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  Каталог ВЛС не указан — доступна только «Вода». «Рельеф» и «Древостой» считаются по
                  облаку точек.
                </div>
              </div>
            )}
            <Button onClick={handleAssess} disabled={!afsDir && !vlsDir}>
              Оценить материалы
            </Button>
          </div>
        </CardPad>
      </Card>

      {/* Метаданные исходных материалов съёмки */}
      {assessed && report && (
        <Card>
          <CardPad>
            <CardHeader
              title="Метаданные исходных материалов"
              subtitle="Считаны из заголовков входящих файлов"
            />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-slate-500">
                    <th className="w-1/3 py-2 pr-4 font-medium">Параметр</th>
                    <th className="py-2 pr-4 font-medium">АФС</th>
                    <th className="py-2 font-medium">ВЛС</th>
                  </tr>
                </thead>
                <tbody>
                  <MetaRow
                    label="Система координат"
                    afs={report.afs ? report.afs.crs : NO_VALUE}
                    vls={report.vls ? report.vls.crs : NO_VALUE}
                  />
                  <MetaRow
                    label="Система высот"
                    tooltip="Может быть указана внутри составной системы координат либо отсутствовать в метаданных."
                    afs={report.afs ? report.afs.vertical_crs ?? UNKNOWN : NO_VALUE}
                    vls={report.vls ? report.vls.vertical_crs ?? UNKNOWN : NO_VALUE}
                  />
                  <MetaRow
                    label="Площадь экстента"
                    afs={report.afs ? `${report.afs.extent_area_km2} км²` : NO_VALUE}
                    vls={report.vls ? `${report.vls.extent_area_km2} км²` : NO_VALUE}
                  />
                  <MetaRow
                    label="Пространственное разрешение"
                    tooltip="Читается только у материалов АФС."
                    afs={report.afs ? `${report.afs.resolution_m} м` : NO_VALUE}
                    vls={NO_VALUE}
                  />
                  <MetaRow
                    label="Плотность точек лазерного отражения"
                    tooltip="Читается только у материалов ВЛС."
                    afs={NO_VALUE}
                    vls={report.vls ? `${report.vls.density_pts_m2} т/м²` : NO_VALUE}
                  />
                </tbody>
              </table>
            </div>
          </CardPad>
        </Card>
      )}

      {/* Потайловая оценка + валидация пар (Блок Д) */}
      {assessed && (
        <Card>
          <CardPad>
            <CardHeader
              title="Оценка материалов по тайлам"
              subtitle={`Целевая СК: ${targetCrs} — считана из АФС; материалы с иной СК приводятся к ней`}
              action={<Layers className="h-4 w-4 text-slate-400" />}
            />
            {detectedCrs ? (
              <div className="mb-3 flex items-center gap-1.5 text-xs text-emerald-600">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                Целевая СК проекта — {detectedCrs} (из метаданных {mode === 'vls-only' ? 'ВЛС' : 'АФС'})
              </div>
            ) : (
              <div className="mb-3 flex items-center gap-1.5 text-xs text-amber-600">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                СК не определена — проверьте файлы
              </div>
            )}
            <div className="mb-3 sm:max-w-xs">
              <Field
                label="Допуск на расхождение углов, м"
                tooltip="У пар с совпадающей СК сверяются координаты нижнего левого угла тайлов АФС и ВЛС. Расхождение больше допуска — предупреждение: тайл остаётся доступен для расчёта, решение за пользователем."
              >
                <NumberInput value={originTolM} step={0.1} min={0} onChange={setOriginTolM} />
              </Field>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-slate-500">
                    <th className="py-2 pr-4">Тайл</th>
                    <th className="py-2 pr-4">АФС (ТИФ)</th>
                    <th className="py-2 pr-4">ВЛС (ЛАС)</th>
                    <th className="py-2 pr-4">Площадь</th>
                    <th className="py-2 pr-4">Нижний левый угол</th>
                    <th className="py-2 pr-4">Валидация пары</th>
                  </tr>
                </thead>
                <tbody>
                  {tiles.map((t) => {
                    const st = pairStatus(t, mode)
                    return (
                      <tr key={t.id} className="border-b last:border-0">
                        <td className="py-2.5 pr-4 font-mono text-xs">{t.name}</td>
                        <td className="py-2.5 pr-4">
                          {t.afs ? (
                            <div className="text-xs">
                              <div className="font-mono text-slate-600">{t.afs.file}</div>
                              <div className="text-slate-500"><span className="text-slate-400">СК:</span> {t.afs.crs} · <span className="text-slate-400">разр:</span> {t.afs.resolution_m} м · {t.afs.size_mb} МБ</div>
                            </div>
                          ) : <span className="text-xs text-slate-400">—</span>}
                        </td>
                        <td className="py-2.5 pr-4">
                          {t.vls ? (
                            <div className="text-xs">
                              <div className="font-mono text-slate-600">{t.vls.file}</div>
                              <div className="text-slate-500"><span className="text-slate-400">СК:</span> {t.vls.crs} · <span className="text-slate-400">плотн:</span> {t.vls.density_pts_m2} т/м²</div>
                              <div className="text-slate-500"><span className="text-slate-400">ТЛО:</span> {t.vls.height_range_m[0]}–{t.vls.height_range_m[1]} м · {t.vls.size_mb} МБ</div>
                              <div className="text-slate-500">
                                <span className="text-slate-400">классы:</span>{' '}
                                {t.vls.classes.length
                                  ? t.vls.classes.map((c) => `${c} — ${CLASS_LABELS[c] ?? 'прочее'}`).join(', ')
                                  : 'нет классификации'}
                              </div>
                            </div>
                          ) : <span className="text-xs text-slate-400">—</span>}
                        </td>
                        <td className="py-2.5 pr-4 font-mono text-xs text-slate-600">{t.area_km2} км²</td>
                        <td className="py-2.5 pr-4 text-xs">
                          {t.afs && <div className="font-mono text-slate-600">АФС {formatOrigin(t.afs.origin)}</div>}
                          {t.vls && <div className="font-mono text-slate-600">ВЛС {formatOrigin(t.vls.origin)}</div>}
                          {(() => {
                            const off = originOffsetM(t)
                            if (off === null) {
                              return <div className="text-slate-400">СК разнятся — сверка после приведения</div>
                            }
                            return off > originTolM
                              ? <div className="text-amber-600">расхождение {off} м</div>
                              : <div className="text-emerald-600">совпадают</div>
                          })()}
                        </td>
                        <td className="py-2.5 pr-4">
                          <div className="flex items-center gap-1.5">
                            {st === 'ok' && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
                            {st === 'reproject' && <AlertTriangle className="h-4 w-4 text-amber-500" />}
                            {st === 'incomplete' && <AlertTriangle className="h-4 w-4 text-slate-400" />}
                            <Badge variant={pairVariant[st]}>{pairLabel[st]}</Badge>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Предупреждения валидации */}
            {(reprojectTiles.length > 0 || shiftedTiles.length > 0 || hasIncomplete) && (
              <div className="mt-3 space-y-2">
                {shiftedTiles.length > 0 && (
                  <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      СК совпадают, но нижние левые углы тайлов АФС и ВЛС разъехались больше
                      допуска ({originTolM} м):{' '}
                      {shiftedTiles.map((r) => `${r.tile.name} — ${r.offset} м`).join(', ')}.
                      Обычно это признак разной нарезки съёмок. Тайлы остаются доступны для расчёта.
                    </div>
                  </div>
                )}
                {reprojectTiles.length > 0 && (
                  <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      СК ВЛС отличается от СК АФС у {reprojectTiles.length} тайлов
                      ({reprojectTiles.map((t) => t.name).join(', ')}). Данные будут приведены
                      к {targetCrs} — целевой СК проекта, считанной из АФС.
                    </div>
                  </div>
                )}
                {hasIncomplete && (
                  <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      Есть неполные пары (нет АФС или ВЛС). Такие тайлы будут пропущены при пакетной обработке.
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Режим работы при неполном комплекте материалов */}
            {mode === 'vls-only' && (
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  АФС не загружены — работаем только с ВЛС. Доступны «Рельеф» и «Древостой» без
                  детекции крон: она выполняется по ортофотоплану. «Вода» недоступна — маску воды
                  строит нейросеть по АФС.
                </div>
              </div>
            )}
            {mode === 'afs-only' && (
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  ВЛС не загружены — доступна только «Вода». «Рельеф» и «Древостой» считаются по
                  облаку точек.
                </div>
              </div>
            )}

            {/* Готовая классификация: влияет на выбор метода в «Рельефе» */}
            {classifiedCount > 0 && (
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                <div>
                  Классификация есть в {classifiedCount} из {vlsCount} файлов ВЛС. Чтобы взять землю
                  из неё вместо собственной классификации, выберите в «Рельефе» метод «Из
                  классификации LAS».
                </div>
              </div>
            )}

            {canProceed && tiles.length > 0 && mode === 'pair' && reprojectTiles.length === 0 && shiftedTiles.length === 0 && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                Все пары валидны. Можно запускать обработку в разделе «Рельеф», «Древостой» или «Вода».
              </div>
            )}
          </CardPad>
        </Card>
      )}
    </div>
  )
}