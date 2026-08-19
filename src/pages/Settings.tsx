import { useSettingsStore } from '@/store/settingsStore'
import { Card, CardPad, CardHeader, Accordion } from '@/components/ui/card'
import { Input, Checkbox, NumberInput, Field } from '@/components/ui/controls'
import { Button } from '@/components/ui/button'

export default function Settings() {
  const { settings, update, updateDeterministic, updateModelPaths, reset } = useSettingsStore()
  const det = settings.deterministic

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1>Настройки</h1>
          <p className="mt-1 text-sm text-slate-500">Глобальные параметры</p>
        </div>
        <Button variant="outline" onClick={reset}>Сбросить</Button>
      </div>

      {/* Пути к моделям */}
      <Card>
        <CardPad>
          <CardHeader title="Пути к моделям" subtitle="Каталоги с весами" />
          <div className="space-y-3">
            <Accordion title="Детекция крон" defaultOpen>
              <Field label="Каталог весов">
                <Input
                  value={settings.model_paths.treecanopy}
                  onChange={(e) => updateModelPaths({ treecanopy: e.target.value })}
                  placeholder="/path/to/treecanopy"
                />
              </Field>
            </Accordion>
            <Accordion title="Сегментация вод" defaultOpen={false}>
              <Field label="Каталог весов">
                <Input
                  value={settings.model_paths.water}
                  onChange={(e) => updateModelPaths({ water: e.target.value })}
                  placeholder="/path/to/water"
                />
              </Field>
            </Accordion>
            <Accordion title="Сегментация болот" defaultOpen={false}>
              <Field label="Каталог весов">
                <Input
                  value={settings.model_paths.swamp}
                  onChange={(e) => updateModelPaths({ swamp: e.target.value })}
                  placeholder="/path/to/swamp"
                />
              </Field>
            </Accordion>
            <Accordion title="Порода / диаметр (опц.)" defaultOpen={false}>
              <Field label="Каталог весов">
                <Input
                  value={settings.model_paths.forest}
                  onChange={(e) => updateModelPaths({ forest: e.target.value })}
                  placeholder="/path/to/forest"
                />
              </Field>
            </Accordion>
          </div>
        </CardPad>
      </Card>

      {/* Каталоги данных */}
      <Card>
        <CardPad>
          <CardHeader title="Рабочие каталоги" />
          <Field label="Каталог данных" className="sm:max-w-md">
            <Input
              value={settings.data_dir}
              onChange={(e) => update({ data_dir: e.target.value })}
              placeholder="/path/to/data"
            />
          </Field>
        </CardPad>
      </Card>

      {/* Детерминизм — общая настройка */}
      <Card>
        <CardPad>
          <CardHeader title="Детерминированный режим" subtitle="Воспроизводимость результатов" />
          <div className="space-y-4">
            <Checkbox
              checked={det.enabled}
              onChange={(v) => updateDeterministic({ enabled: v })}
              label="Включить детерминированный режим"
            />
            <div className={`space-y-4 ${det.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Seed" tooltip="Фиксированное значение seed для генератора случайных чисел. При одинаковом seed результаты идентичны." className="flex-1">
                  <NumberInput value={det.seed} min={0} onChange={(v) => updateDeterministic({ seed: v })} />
                </Field>
                <Field label="DataLoader num_workers">
                  <NumberInput value={det.num_workers} onChange={(v) => updateDeterministic({ num_workers: v })} min={0} />
                </Field>
              </div>
              <div className="flex flex-wrap gap-4">
                <Checkbox checked={det.cudnn_deterministic} onChange={(v) => updateDeterministic({ cudnn_deterministic: v })} label="cudnn.deterministic" />
                <Checkbox checked={!det.cudnn_benchmark} onChange={(v) => updateDeterministic({ cudnn_benchmark: !v })} label="cudnn.benchmark = False" />
              </div>
            </div>
          </div>
        </CardPad>
      </Card>
    </div>
  )
}