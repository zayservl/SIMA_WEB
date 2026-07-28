# План: СИМА v2 — правки по рецензии аналитика и заказчика

> **Slug**: sima-v2-reviewer-feedback
> **Базовая ветка**: `zayservl/feature/dem-computational-library` (последние исправления backend/relief-demo лежат там, НЕ main)
> **Новая ветка**: `feature/v2-reviewer-feedback` (создаётся ОТ `zayservl/feature/dem-computational-library`)
> **Старт**: `git fetch origin && git checkout zayservl/feature/dem-computational-library && git pull && git checkout -b feature/v2-reviewer-feedback`
> **Коммиты**: атомарные по группам, ~10 коммитов

## TL;DR (Для человека)

Внесены правки в прототип СИМА по двум источникам: ФТ аналитика (5 общих + 10 по Древостою + 4 по Воде + 2 по Задачам + 1 по Данным + 1 по Параметрам) и Q&A с заказчиком. Ключевые решения: СК — readOnly из метаданных (ручное изменение невозможно, загрузка пользовательской СК — будущее требование); размер тайла не выводим на пользователя нигде; Гари/Ветровалы убираем полностью (не объединяем); перезапуск одного тайла и упавших убираем, добавляем «Пересчитать упавшие/все с новыми параметрами» (новая сессия); результаты — только в рамках проекта. Каждое изменение — атомарный коммит. Тестируем на пользовательский путь: загрузка → рельеф → древостой → вода → задачи → данные.

## Контекст решений (из допроса)

| Развилка | Решение |
|----------|---------|
| Перезапуск тайлов | Убрать перезапуск одного тайла + упавших. Добавить «Пересчитать упавшие с новыми параметрами» и «Пересчитать все с новыми параметрами» (оба — новый job). |
| «Карта высот растительности» (Древостой 4) | Это заголовок раздела «ЦММ», не пункт. Под ним подпункты 1-6. |
| Гари/Ветровалы | Убрать полностью (ошибка аналитика), не объединять. |
| Сглаживание/Разрешение | Выпадающий список предустановок + экспертные числовые поля. |
| ЦМР vs карта рельефов | Два разных входа: ЦМР (DSM/DTM) + производные (уклоны/экспозиции/TPI). |
| Результаты между проектами | Нет, только в рамках проекта. |
| Размер тайла | Не выводим на пользователя нигде (ошибка в ФТ). |
| Горизонтали | Убрать только горизонтали (0.5/2/5/10 м), TIN оставить. |
| Пользовательская СК | Будущее требование. СК — readOnly из метаданных. Ручное изменение невозможно. |
| Git | Одна ветка, атомарные коммиты по группам (~10). |

## Порядок коммитов и задач

### Группа 1. Контракты и стор — обновление типов
**Коммит**: `feat(types): v2 contracts — smoothing/resolution presets, readOnly CRS, dual-source forest, task recompute model`

- [x] **1.1** `src/api/types.ts`: добавить `SmoothingPreset = 'none' | 'light' | 'medium' | 'strong'` и `ResolutionPreset = 'native' | '0.1m' | '0.25m' | '0.5m' | '1m' | '2m'`. Добавить поля `smoothing_preset: SmoothingPreset` и `output_resolution_preset: ResolutionPreset` в `ReliefParams`, `ForestParams`, `WaterParams`. Обновить `ForestParams`: убрать `detection.sample_size`, `detection.bound`, `detection.method='both'`; переименовать `detection.season` → `detection.vegetation_state: 'active' | 'absent'`; убрать `extras.tlo`, `extras.peaks`, `extras.peak_size`, `extras.fire`, `extras.fire_res`, `extras.fire_sm`, `extras.wind`, `extras.wind_res`, `extras.wind_sm` (весь блок `extras`). Добавить `ReliefSource = { kind: 'system' | 'upload'; system_session_id?: string; upload_path?: string }` и `ReliefDerivativesSource` (тот же тип) — два поля в `ForestParams`: `dsm_source: ReliefSource` и `derivatives_source: ReliefDerivativesSource`. Добавить `ForestDsmSource` в `WaterParams`: `cmd_source: { kind: 'system' | 'upload'; system_session_id?: string; upload_path?: string }`. Добавить `LoggingCategoryTable` — 4 строки × 3 колонки (Высота дерева, Уклон, Плотность), значения по умолчанию. В `Job` добавить `recompute_of?: string` (id исходного job, если это пересчёт). Убрать `swamp` и `buffers` из `WaterParams` (блоки Болота и Охранные зоны). Убрать `segment.sample_size`, `segment.bound`, `segment.resolution` из `WaterParams`. В `Scene` сделать `target_crs` readOnly-семантику (поле остаётся, но UI не редактирует — только отображает). — **REF**: `src/api/types.ts` — **ACCEPT**: tsc проходит, новые типы используются в страницах. — **QA**: `npx tsc --noEmit` без ошибок.
- [x] **1.2** `src/store/projectStore.ts`: обновить `defaultReliefParams`, `defaultForestParams`, `defaultWaterParams` под новые контракты. Добавить `recomputeJob(jobId, tileIds?, newParams)` — создаёт новый job с `recompute_of=jobId`, копирует только указанные тайлы (или все). Убрать `restartTile` и `restartFailedTiles` из стора. — **REF**: `src/store/projectStore.ts` — **ACCEPT**: стор компилируется, `recomputeJob` создаёт новый job. — **QA**: `npx tsc --noEmit` без ошибок.

### Группа 2. Общий компонент ModuleHeader
**Коммит**: `feat(ui): ModuleHeader — readOnly CRS display, smoothing/resolution presets, method tooltips, dependency checks`

- [x] **2.1** `src/components/ui/ModuleHeader.tsx` (новый): компонент-шапка для каждой страницы модуля. Содержит: (а) readOnly отображение СК проекта (из `project.scene.target_crs`, если пусто — «не определена, загрузите файлы»); (б) выпадающий список «Сглаживание» (`SmoothingPreset`); (в) выпадающий список «Разрешение выходного файла» (`ResolutionPreset`) + предупреждение если `output_resolution_preset` мельче разрешения АФС/ВЛС; (г) слот для тултипов методов; (д) блок проверки зависимостей (см. 2.2). — **REF**: `src/components/ui/ModuleHeader.tsx`, `src/components/ui/controls.tsx` (использует `Select`) — **ACCEPT**: компонент рендерит все 5 элементов, СК readOnly. — **QA**: `npx tsc --noEmit`; визуальная проверка на Relief.
- [x] **2.2** `src/lib/dependencies.ts` (новый): функция `checkDependencies(projectId, module: 'relief' | 'forest' | 'water')` — возвращает `{ ok: boolean; missing: { layer: string; tab: string }[] }`. Рельеф: требует АФС+ВЛС загружены. Древостой: требует Рельеф посчитан (есть job type=relief со статусом success) ИЛИ загружен пользовательский .geotiff. Вода: требует Древостой посчитан (job type=forest, status=success) ИЛИ загружен пользовательский .geotiff. — **REF**: `src/lib/dependencies.ts`, `src/store/projectStore.ts` — **ACCEPT**: функция возвращает корректные пропуски. — **QA**: unit-проверка моком (3 сценария: всё есть, нет рельефа, нет древостоя).
- [x] **2.3** `src/lib/methodTooltips.ts` (новый): справочник текстов тултипов для всех методов (SMRF, manual, stat, range, kmeans, CHM, ITS, DEN, сегментация воды, и т.д.). Каждый — 1-2 предложения о принципе работы. — **REF**: `src/lib/methodTooltips.ts` — **ACCEPT**: справочник покрыт для всех `FilterMethod` + ключевых параметров Forest/Water. — **QA**: `npx tsc --noEmit`.

### Группа 3. Upload — СК из метаданных, .geotiff ЦМР
**Коммит**: `feat(upload): read CRS from metadata, add .geotiff DSM upload slot`

- [x] **3.1** `src/pages/Upload.tsx`: при оценке материалов считать СК из первого валидного тайла (АФС или ВЛС) и записать в `project.scene.target_crs` через `updateScene`. Если СК АФС и ВЛС различаются — предупреждение + использовать СК АФС как основную (демо-логика). Добавить третий слот загрузки: «ЦМР (GeoTIFF/BigTIFF) — опционально» для загруженной пользователем цифровой модели рельефа. Валидация: только `.geotiff`/`.tif`/`.tiff`. — **REF**: `src/pages/Upload.tsx`, `src/store/projectStore.ts` — **ACCEPT**: СК записывается в сцену, третий слот есть с валидацией расширения. — **QA**: `npx tsc --noEmit`; мок-сценарий: загрузка → оценка → СК в сцене.

### Группа 4. Relief — убрать горизонтали, ModuleHeader
**Коммит**: `feat(relief): remove horizontals, add ModuleHeader with presets & tooltips`

- [x] **4.1** `src/pages/Relief.tsx`: вставить `<ModuleHeader module="relief" .../>` в начало. Убрать блок «Горизонтали» (чекбоксы 0.5/2/5/10 м). Оставить TIN (DXF). Добавить `InfoHint` ко всем методам фильтрации (SMRF, manual, stat, range, kmeans) из `methodTooltips`. Сглаживание: выпадающий список предустановок + существующие числовые поля (sigma/order/window) под предустановкой. — **REF**: `src/pages/Relief.tsx`, `src/components/ui/ModuleHeader.tsx` — **ACCEPT**: ModuleHeader рендерится, горизонтали убраны, TIN есть, тултипы на методах. — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 5. Forest — два входа, убрать параметры, таблица рубки
**Коммит**: `feat(forest): dual DSM+derivatives source, remove density/tile/overlap/both/extras, add logging table`

- [x] **5.1** `src/pages/Forest.tsx`: вставить `<ModuleHeader module="forest" .../>`. Добавить два переключателя источника: (1) «Источник ЦМР» — radio: «Рассчитанная в системе» (выпадающий список завершённых job type=relief) / «Загрузить .geotiff» (input file + валидация расширения); (2) «Источник производных рельефа» — аналогично. Убрать из блока «Цифровая модель древостоя»: параметры «Плотность» (channel `den`) и «Интенсивность» (channel `its`) — оставить только CHM. Убрать из блока «Детекция крон»: «Размер тайла» и «Перекрытие». Переименовать «Сезон» → «Состояние вегетации» с опциями «Активная»/«Отсутствует». Убрать опцию «Оба метода» из детекции крон. Полностью убрать блок «Дополнительные слои» (Гари, Ветровалы, Сохранение ТЛО, Пики — всё). Гари/Ветровалы не реализуем на данном этапе — не вводим пользователя в заблуждение (ошибка аналитика, не объединяем, а убираем целиком). В блок «Категория рубки» добавить редактируемую таблицу 4×3 (Высота дерева, Уклон, Плотность × 1/2/3/4 категории) со значениями по умолчанию. — **REF**: `src/pages/Forest.tsx`, `src/api/types.ts` — **ACCEPT**: два входа, убранные параметры отсутствуют, таблица есть и редактируется. — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 6. Water — вход ЦМД, убрать параметры
**Коммит**: `feat(water): add CMD source, remove overlap/resolution/swamp/buffers/tile-size`

- [x] **6.1** `src/pages/Water.tsx`: вставить `<ModuleHeader module="water" .../>`. Добавить переключатель «Источник ЦМД» — radio: «Рассчитанная в системе» (выпадающий список завершённых job type=forest) / «Загрузить .geotiff» (input + валидация). Убрать из «Сегментация»: «Перекрытие», «Разрешение», «Размер тайла». Полностью убрать блок «Болота». Полностью убрать блок «Охранные зоны». — **REF**: `src/pages/Water.tsx`, `src/api/types.ts` — **ACCEPT**: вход ЦМД есть, убранные блоки отсутствуют. — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 7. Tasks — модель пересчёта
**Коммит**: `feat(tasks): remove single-tile & failed restarts, add recompute-failed/recompute-all with new params`

- [x] **7.1** `src/pages/Tasks.tsx`: убрать контекстное действие «Перезапустить тайл» на строке тайла (кнопка Play). Убрать групповую кнопку «Упавшие» (restartFailedTiles). Кнопку «С новыми параметрами» переименовать в «Пересчитать с новыми параметрами» — открывает форму параметров (как сейчас), создаёт новый job через `recomputeJob(jobId, undefined, newParams)` (все тайлы). Добавить новую кнопку «Пересчитать упавшие с новыми параметрами» — открывает форму параметров, создаёт новый job через `recomputeJob(jobId, failedTileIds, newParams)` (только упавшие). Кнопка «Остановить тайл» (running) — остаётся. В карточке job, если `recompute_of`, показать ссылку «пересчёт от \u003cисходный job\u003e». — **REF**: `src/pages/Tasks.tsx`, `src/store/projectStore.ts` — **ACCEPT**: нет перезапуска одного тайла, нет «Упавшие», есть «Пересчитать с новыми параметрами» и «Пересчитать упавшие с новыми параметрами». — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 8. Data — просмотр параметров запуска
**Коммит**: `feat(data): show job run parameters in session card`

- [x] **8.1** `src/pages/Data.tsx`: в `SessionCard` добавить третий таб «Параметры» (между «Файлы» и «Лог»). Таб рендерит `job.params` в виде человекочитаемых пар ключ-значение (рекурсивный рендерер для вложенных объектов). Метки на русском. — **REF**: `src/pages/Data.tsx` — **ACCEPT**: таб «Параметры» рендерит все поля `job.params`. — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 9. ProjectSettings — СК readOnly
**Коммит**: `feat(project-settings): make CRS readOnly, remove manual change, remove reprojection toggle`

- [x] **9.1** `src/pages/ProjectSettings.tsx`: заменить `<select>` для СК на readOnly-отображение (текст + иконка Globe). Если СК не определена — «Загрузите файлы, СК будет считана автоматически». Убрать чекбокс «Привести съёмки к целевой СК» (поскольку СК теперь readOnly и не меняется). Оставить блок «Воспроизводимость» (детерминизм/seed) без изменений. — **REF**: `src/pages/ProjectSettings.tsx` — **ACCEPT**: СК не редактируется, чекбокса приведения нет. — **QA**: `npx tsc --noEmit`; визуальная проверка.

### Группа 10. Блокировки зависимостей в модулях
**Коммит**: `feat(dependencies): block module run when prerequisite layers missing, show guidance tooltip`

- [x] **10.1** Во все три страницы (Relief, Forest, Water) интегрировать `checkDependencies` из `src/lib/dependencies.ts`. Если `checkDependencies` возвращает `ok: false` — кнопка «Запустить» disabled + тултип с текстом: «Не хватает: \u003cсписок missing.layer\u003e. Рассчитайте на вкладке \u003cmissing.tab\u003e.» Для Forest: если выбрана «Рассчитанная в системе» для ЦМР/производных и нет завершённого job type=relief — блокировка. Для Water: аналогично для job type=forest. — **REF**: `src/pages/Relief.tsx`, `src/pages/Forest.tsx`, `src/pages/Water.tsx`, `src/lib/dependencies.ts` — **ACCEPT**: кнопка disabled при отсутствии данных, тултип показывает что и где рассчитать. — **QA**: `npx tsc --noEmit`; мок-сценарии: нет рельефа → Forest заблокирован; нет древостоя → Water заблокирован; всё есть → не заблокированы.

## Must-NOT-Have (границы)
- НЕ реализуем загрузку пользовательской СК (будущее требование).
- НЕ выводим «Размер тайла» на пользователя нигде (Relief/Forest/Water).
- НЕ реализуем обмен результатами между проектами.
- НЕ реализуем перезапуск одного произвольного тайла.
- НЕ добавляем Гари/Ветровалы обратно (не реализуем на данном этапе — не вводим пользователя в заблуждение).
- НЕ добавляем горизонтали обратно.
- НЕ трогаем backend/ (только FE прототип).
- НЕ добавляем новые зависимости в package.json (всё на существующих react/zustand/lucide).

## Зависимости между задачами
```
1 (types/store) → 2 (ModuleHeader) → 3,4,5,6 (страницы)
1 → 7 (Tasks: recomputeJob в стору)
1 → 8 (Data: новые типы params)
1 → 9 (ProjectSettings: Scene.target_crs readOnly)
2 → 10 (dependencies.ts используется ModuleHeader)
7 зависит от 1 (recomputeJob в стору)
10 зависит от 2 (checkDependencies) и 4,5,6 (интеграция)
```

## Пользовательский путь для тестирования
1. Создать проект → Загрузить данные → СК считана в сцену (readOnly в ProjectSettings).
2. Открыть Relief → ModuleHeader показывает СК → тултипы на методах → горизонтали убраны, TIN есть → Запустить.
3. Открыть Forest → заблокирован (нет рельефа) → тултип «Рассчитайте на вкладке Рельеф».
4. Вернуться в Relief → дождаться success → открыть Forest → разблокирован → выбрать ЦМР из системы → убрать Плотность/Интенсивность/Размер тайла/Перекрытие/Оба метода → таблица рубки редактируется → Запустить.
5. Открыть Water → заблокирован (нет древостоя) → дождаться Forest success → разблокирован → выбрать ЦМД из системы → убрать Перекрытие/Разрешение/Болота/Охранные зоны → Запустить.
6. Открыть Tasks → нет перезапуска одного тайла → «Пересчитать упавшие с новыми параметрами» → новый job → «Пересчитать с новыми параметрами» → новый job.
7. Открыть Data → таб «Параметры» показывает параметры запуска.