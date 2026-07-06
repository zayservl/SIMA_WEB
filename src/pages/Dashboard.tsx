import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { Card, CardPad } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Plus, MapPin } from 'lucide-react'
import type { ProjectStatus } from '@/api/types'

const statusVariant: Record<ProjectStatus, 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  empty: 'neutral', uploaded: 'info', processing: 'warning', done: 'success', error: 'danger',
}
const statusLabel: Record<ProjectStatus, string> = {
  empty: 'пусто', uploaded: 'данные загружены', processing: 'обработка', done: 'готово', error: 'ошибка',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const projects = useProjectStore((s) => s.projects)
  const assessment = useProjectStore((s) => s.assessment)
  const createProject = useProjectStore((s) => s.createProject)

  const handleCreate = () => {
    const p = createProject('Новый проект ' + new Date().toLocaleDateString('ru-RU'))
    navigate(`/projects/${p.id}/upload`)
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1>Проекты</h1>
          <p className="mt-1 text-sm text-slate-500">Выберите проект или создайте новый</p>
        </div>
        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4" /> Новый проект
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((p) => {
          const a = assessment[p.id]
          return (
            <Card key={p.id} className="cursor-pointer transition-all hover:border-brand-300 hover:shadow-md">
              <CardPad>
                <div onClick={() => navigate(`/projects/${p.id}/upload`)}>
                  <div className="mb-3 flex items-start justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">{p.name}</h3>
                    <Badge variant={statusVariant[p.status]}>{statusLabel[p.status]}</Badge>
                  </div>
                  <p className="mb-3 text-xs text-slate-400">{new Date(p.created_at).toLocaleDateString('ru-RU')}</p>
                  {a && (a.afs || a.vls) && (
                    <div className="space-y-1.5 border-t border-slate-100 pt-3">
                      {a.afs && (
                        <div className="flex items-center gap-2 text-xs text-slate-600">
                          <MapPin className="h-3 w-3 text-blue-500" />
                          <span>АФС: {a.afs.resolution_m} м/px · {a.afs.extent_area_km2} км²</span>
                        </div>
                      )}
                      {a.vls && (
                        <div className="flex items-center gap-2 text-xs text-slate-600">
                          <MapPin className="h-3 w-3 text-green-500" />
                          <span>ВЛС: {a.vls.density_pts_m2} т/м² · Z {a.vls.tlo_height_range_m[0]}–{a.vls.tlo_height_range_m[1]} м</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </CardPad>
            </Card>
          )
        })}
      </div>
    </div>
  )
}