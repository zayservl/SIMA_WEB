import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input, Field } from '@/components/ui/controls'
import { Badge } from '@/components/ui/badge'
import { FolderOpen, AlertTriangle, CheckCircle2, XCircle, Layers } from 'lucide-react'
import type { MaterialAssessment } from '@/api/types'

// ---- Потайловая модель входных материалов (Блок Д) -----------------------

interface InputAfs { file: string; crs: string; resolution_m: number; size_mb: number }
interface InputVls { file: string; crs: string; density_pts_m2: number; height_range_m: [number, number]; size_mb: number }

interface InputTile {
  id: string
  name: string // общий номер пары, напр. tile_001
  afs: InputAfs | null
  vls: InputVls | null
  area_km2: number
}

const TARGET_CRS = 'EPSG:32637'

// Демо-набор пар ТИФ+ЛАС. Включает: совпадающие пары, пары с несовпадением СК
// (демонстрация валидации), пару без ВЛС (неполная).
function generateMockInputTiles(): InputTile[] {
  const tiles: InputTile[] = []
  for (let i = 1; i <= 24; i++) {
    const id = `in-${String(i).padStart(3, '0')}`
    const name = `tile_${String(i).padStart(3, '0')}`
    const afsFile = `${String(i * 100).padStart(6, '0')}.tif`
    const vlsFile = `pt${String(i * 100).padStart(6, '0')}.las`
    const afsSize = 130 + ((i * 7) % 30)
    const vlsSize = 115 + ((i * 5) % 25)
    const density = 4000 + ((i * 37) % 1000)
    const hMin = +(15 + ((i * 0.5) % 30)).toFixed(2)
    const hMax = +(950 + ((i * 3) % 200)).toFixed(2)

    let afsCrs = TARGET_CRS
    let vls: InputVls | null = {
      file: vlsFile, crs: TARGET_CRS, density_pts_m2: density, height_range_m: [hMin, hMax], size_mb: vlsSize,
    }

    if (i === 21 || i === 22) {
      // СК не совпадает внутри пары → валидация подсветит это
      afsCrs = 'EPSG:4326'
    } else if (i === 23) {
      // Неполная пара: нет ВЛС
      vls = null
    }

    tiles.push({
      id, name, area_km2: 1.0,
      afs: { file: afsFile, crs: afsCrs, resolution_m: 0.14, size_mb: afsSize },
      vls,
    })
  }
  return tiles
}

type PairStatus = 'ok' | 'reproject' | 'mismatch' | 'incomplete'

function pairStatus(t: InputTile, reproject: boolean): PairStatus {
  if (!t.afs || !t.vls) return 'incomplete'
  if (t.afs.crs === t.vls.crs) return 'ok'
  return reproject ? 'reproject' : 'mismatch'
}

const pairLabel: Record<PairStatus, string> = {
  ok: 'СК совпадают',
  reproject: 'СК разнятся → приведение',
  mismatch: 'СК не совпадают',
  incomplete: 'Неполная пара',
}
const pairVariant: Record<PairStatus, 'success' | 'warning' | 'danger' | 'neutral'> = {
  ok: 'success', reproject: 'warning', mismatch: 'danger', incomplete: 'neutral',
}

// Сводный отчёт для совместимости со стором (MaterialAssessment) — агрегат по тайлам.
function aggregate(tiles: InputTile[]): MaterialAssessment {
  const afsTiles = tiles.filter((t) => t.afs)
  const vlsTiles = tiles.filter((t) => t.vls)
  return {
    afs: afsTiles.length ? {
      crs: TARGET_CRS,
      extent_area_km2: +afsTiles.reduce((a, t) => a + t.area_km2, 0).toFixed(2),
      resolution_m: Math.min(...afsTiles.map((t) => t.afs!.resolution_m)),
      ofp_scale: '1:1400',
      tiles_total: afsTiles.length, tiles_ok: afsTiles.length, tiles_failed: 0, failed_tiles: [],
    } : null,
    vls: vlsTiles.length ? {
      crs: TARGET_CRS,
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

export default function Upload() {
  const { projectId } = useParams()
  const setAssessment = useProjectStore((s) => s.setAssessment)
  const updateScene = useProjectStore((s) => s.updateScene)
  const projects = useProjectStore((s) => s.projects)
  const project = projects.find((p) => p.id === projectId)

  const [afsDir, setAfsDir] = useState(project?.scene.afs_dir || '')
  const [vlsDir, setVlsDir] = useState(project?.scene.vls_dir || '')
  const [tiles, setTiles] = useState<InputTile[]>([])
  const [assessed, setAssessed] = useState(false)
  const [detectedCrs, setDetectedCrs] = useState<string | null>(null)

  const reproject = project?.scene.reproject ?? true
  const targetCrs = project?.scene.target_crs || TARGET_CRS

  const handleAssess = () => {
    if (!projectId) return
    const generated = generateMockInputTiles()
    setTiles(generated)
    setAssessment(projectId, aggregate(generated))

    // СК из первого валидного тайла: АФС приоритетнее ВЛС.
    const afsTile = generated.find((t) => t.afs)
    const vlsTile = generated.find((t) => t.vls)
    const afsCrs = afsTile?.afs?.crs ?? null
    const vlsCrs = vlsTile?.vls?.crs ?? null
    const detected = afsCrs ?? vlsCrs
    setDetectedCrs(detected)

    if (detected && projectId) {
      updateScene(projectId, { target_crs: detected })
    }

    setAssessed(true)
  }

  const statuses = tiles.map((t) => pairStatus(t, reproject))
  const hasMismatch = statuses.includes('mismatch')
  const hasReproject = statuses.includes('reproject')
  const hasIncomplete = statuses.includes('incomplete')
  const canProceed = !hasMismatch && !hasIncomplete

  const afsCrsList = tiles.filter((t) => t.afs).map((t) => t.afs!.crs)
  const vlsCrsList = tiles.filter((t) => t.vls).map((t) => t.vls!.crs)
  const afsCrsSet = new Set(afsCrsList)
  const vlsCrsSet = new Set(vlsCrsList)
  const afsVlsCrsMismatch = assessed && afsCrsSet.size > 0 && vlsCrsSet.size > 0
    && [...afsCrsSet].some((c) => !vlsCrsSet.has(c))

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
            <Field label="Каталог АФС (.tif, .tiff — GeoTIFF/BigTIFF)">
              <div className="flex gap-2">
                <FolderOpen className="mt-2 h-4 w-4 shrink-0 text-slate-400" />
                <Input
                  value={afsDir}
                  onChange={(e) => { setAfsDir(e.target.value); setAssessed(false) }}
                  placeholder="/data/afs"
                />
              </div>
            </Field>
            <Field label="Каталог ВЛС (.las — LAS 1.2)">
              <div className="flex gap-2">
                <FolderOpen className="mt-2 h-4 w-4 shrink-0 text-slate-400" />
                <Input
                  value={vlsDir}
                  onChange={(e) => { setVlsDir(e.target.value); setAssessed(false) }}
                  placeholder="/data/vls"
                />
              </div>
            </Field>
            <Button onClick={handleAssess} disabled={!afsDir && !vlsDir}>
              Оценить материалы
            </Button>
          </div>
        </CardPad>
      </Card>

      {/* Потайловая оценка + валидация пар (Блок Д) */}
      {assessed && (
        <Card>
          <CardPad>
            <CardHeader
              title="Оценка материалов по тайлам"
              subtitle={`Целевая СК: ${targetCrs} · приведение ${reproject ? 'включено' : 'выключено'}`}
              action={<Layers className="h-4 w-4 text-slate-400" />}
            />
            {detectedCrs ? (
              <div className="mb-3 flex items-center gap-1.5 text-xs text-emerald-600">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                СК считана из метаданных: {detectedCrs}
              </div>
            ) : (
              <div className="mb-3 flex items-center gap-1.5 text-xs text-amber-600">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                СК не определена — проверьте файлы
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-slate-500">
                    <th className="py-2 pr-4">Тайл</th>
                    <th className="py-2 pr-4">АФС (ТИФ)</th>
                    <th className="py-2 pr-4">ВЛС (ЛАС)</th>
                    <th className="py-2 pr-4">Площадь</th>
                    <th className="py-2 pr-4">Валидация пары</th>
                  </tr>
                </thead>
                <tbody>
                  {tiles.map((t) => {
                    const st = pairStatus(t, reproject)
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
                            </div>
                          ) : <span className="text-xs text-slate-400">—</span>}
                        </td>
                        <td className="py-2.5 pr-4 font-mono text-xs text-slate-600">{t.area_km2} км²</td>
                        <td className="py-2.5 pr-4">
                          <div className="flex items-center gap-1.5">
                            {st === 'ok' && <CheckCircle2 className="h-4 w-4 text-emerald-500" />}
                            {st === 'reproject' && <AlertTriangle className="h-4 w-4 text-amber-500" />}
                            {st === 'mismatch' && <XCircle className="h-4 w-4 text-red-500" />}
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
            {(hasMismatch || hasReproject || hasIncomplete) && (
              <div className="mt-3 space-y-2">
                {hasMismatch && (
                  <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-xs text-red-700">
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      Есть пары с несовпадающей СК, а приведение выключено. Включите «Привести к целевой СК» в «Параметрах проекта» — иначе алгоритм отработает некорректно (опыт: «в разных СК не работает»).
                    </div>
                  </div>
                )}
                {hasReproject && (
                  <div className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-700">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <div>
                      Есть пары с разной СК у АФС и ВЛС — они будут приведены к {targetCrs} перед обработкой.
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

            {canProceed && tiles.length > 0 && (
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