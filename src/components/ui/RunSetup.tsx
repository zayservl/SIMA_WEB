// Общий блок «Запуск расчёта» для страниц Рельеф/Древостой/Вода: имя расчёта.
// Одинаков для всех модулей, поэтому вынесен из страниц в один компонент.

import { Card, CardPad, CardHeader } from '@/components/ui/card'
import { Field, Input } from '@/components/ui/controls'

export function RunSetup({ name, onNameChange }: {
  name: string
  onNameChange: (v: string) => void
}) {
  return (
    <Card>
      <CardPad>
        <CardHeader title="Запуск расчёта" />
        <Field
          label="Название расчёта"
          hint="Как расчёт будет назван в очереди задач и в менеджере данных. Имя можно изменить позже."
          className="sm:max-w-md"
        >
          <Input value={name} onChange={(e) => onNameChange(e.target.value)} />
        </Field>
      </CardPad>
    </Card>
  )
}
