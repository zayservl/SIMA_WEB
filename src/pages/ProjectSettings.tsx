import { useParams } from 'react-router-dom'
import { useProjectStore } from '@/store/projectStore'
import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Input, Checkbox, NumberInput, Field } from '@/components/ui/controls'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Globe, Shuffle } from 'lucide-react'

// Параметры проекта: целевая СК, приведение съёмок, детерминизм/seed.
// Ранее дублировались в Upload и Relief — теперь единое место, сохраняется
// в scene проекта (контракт Scene в api/types.ts).
export default function ProjectSettings() {
  const { projectId } = useParams()
  const projects = useProjectStore((s) => s.projects)
  const updateScene = useProjectStore((s) => s.updateScene)
  const updateProject = useProjectStore((s) => s.updateProject)
  const { settings } = useSettingsStore()

  const project = projects.find((p) => p.id === projectId)
  if (!project) {
    return <div className="text-sm text-slate-500">Проект не найден.</div>
  }

  const scene = project.scene
  const targetCrs = scene.target_crs || settings.default_target_crs
  const deterministic = scene.deterministic ?? settings.deterministic.enabled
  const seed = scene.seed ?? settings.deterministic.seed

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1>Параметры проекта</h1>
        <p className="mt-1 text-sm text-slate-500">Целевая СК, приведение съёмок и воспроизводимость — применяются ко всем модулям конвейера</p>
      </div>

      {/* Название */}
      <Card>
        <CardPad>
          <CardHeader title="Проект" />
          <Field label="Название проекта">
            <Input
              value={project.name}
              onChange={(e) => updateProject(project.id, { name: e.target.value })}
            />
          </Field>
        </CardPad>
      </Card>

      {/* Целевая СК */}
      <Card>
        <CardPad>
          <CardHeader title="Приведение съёмок" subtitle="СК считывается из метаданных загруженных файлов" action={<Globe className="h-4 w-4 text-slate-400" />} />
          <div className="space-y-4">
            <Field label="Целевая система координат">
              <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <Globe className="h-4 w-4 text-slate-400" />
                <span className={cn('text-slate-700', !targetCrs && 'text-amber-600')}>
                  {targetCrs || 'Загрузите файлы, СК будет считана автоматически'}
                </span>
              </div>
            </Field>
          </div>
        </CardPad>
      </Card>

      {/* Детерминизм */}
      <Card>
        <CardPad>
          <CardHeader title="Воспроизводимость" subtitle="Детерминированный режим" action={<Shuffle className="h-4 w-4 text-slate-400" />} />
          <div className="space-y-4">
            <Checkbox
              checked={deterministic}
              onChange={(v) => updateScene(project.id, { deterministic: v })}
              label="Детерминированный режим (идентичные результаты при одинаковом seed)"
            />
            <div className={`grid gap-4 sm:grid-cols-2 ${deterministic ? '' : 'opacity-40 pointer-events-none'}`}>
              <Field label="Seed" hint="Фиксированное значение ГПСЧ. При одинаковом seed результаты идентичны.">
                <NumberInput value={seed} min={0} onChange={(v) => updateScene(project.id, { seed: v })} />
              </Field>
              <div className="flex items-end text-xs text-slate-500">
                Флаги cudnn.deterministic / benchmark берутся из глобальных настроек.
              </div>
            </div>
          </div>
        </CardPad>
      </Card>

      <div className="flex justify-end">
        <Button variant="outline" onClick={() => window.history.back()}>Готово</Button>
      </div>
    </div>
  )
}