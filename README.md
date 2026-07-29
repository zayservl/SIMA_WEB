# СИМА

Система обработки данных дистанционного зондирования: воздушное лазерное сканирование (ВЛС)
и аэрофотосъёмка (АФС) → цифровые модели рельефа/местности (ЦМР/ЦММ), древостой, гидрография.

Репозиторий состоит из двух независимых частей:

```
sima-web/
├── src/         # Frontend — веб-прототип интерфейса (React + TypeScript)
├── backend/     # Backend — вычислительная Python-библиотека обработки ЦМР/ЦММ
└── public/, dist/, screenshots/  # статика, сборка, скриншоты интерфейса
```

## Frontend (src/)

Веб-прототип интерфейса СИМА: управление проектами, загрузка данных ВЛС/АФС,
настройка параметров расчётов (Рельеф / Древостой / Вода), мониторинг задач по тайлам,
менеджер выходных данных.

**Стек:** React 18 + TypeScript, Vite, React Router, Zustand (состояние + persist в
localStorage), Tailwind CSS, lucide-react.

**Статус:** UI-прототип на моках — расчёты не выполняются, задачи и результаты
эмулируются в браузерном сторе (`src/store/`). Прямой интеграции с `backend/` пока нет
(HTTP-клиента к бэкенду в коде нет); контракты параметров в `src/api/types.ts` спроектированы
как единый источник для будущей интеграции с `sima-relief-service`.

### Запуск

```bash
npm install
npm run dev        # dev-сервер (Vite)
npm run build       # tsc + сборка в dist/
npm run preview     # предпросмотр сборки
```

### Структура

- `src/pages/` — экраны: Dashboard, Upload, Relief, Forest, Water, Tasks, Data, ProjectSettings, Settings
- `src/store/` — Zustand-сторы (`projectStore`, `settingsStore`) с персистентностью в localStorage
- `src/components/` — layout (Sidebar/Topbar/AppShell) и UI-кит (`components/ui/`)
- `src/api/types.ts` — контракты данных (проекты, задачи, параметры модулей, артефакты)
- `src/lib/` — вспомогательная логика (проверка зависимостей между этапами, CRS, тайлы)

Скриншоты интерфейса — в [screenshots/](screenshots/).

## Backend (backend/)

Вычислительная Python-библиотека обработки ЦМР (DTM) / ЦММ (DSM) и их производных
(уклон, экспозиция, TPI, горизонтали, TIN) из облаков точек ВЛС (LAS) и АФС (GeoTIFF).
Порт из legacy QGIS-плагина в чистый Python, без зависимости от QGIS/PyQt5.

Организована как 4 отдельных pip-устанавливаемых пакета (`packages/sima-dem-core`,
`sima-dem-ground`, `sima-dem-dsm`, `sima-relief-service`) поверх GDAL/PDAL/rasterio/laspy/scipy —
подробности, установка, API и параметры конвейера см. в [backend/README.md](backend/README.md).

Демонстрационный кейс (`backend/relief_demo.ipynb`, `backend/run_dsm_demo.py`) прогоняет
полный конвейер «Анализ рельефа» на тестовых датасетах и сравнивает результат с эталоном.

## Документы

- [REFINEMENT_PLAN.md](REFINEMENT_PLAN.md) — план доработок интерфейса-прототипа
- [CORRESPONDENCE.md](CORRESPONDENCE.md) — переписка/контекст по проекту
- `Архитектурная концепция.pdf`, `Концептуализация работ на Q3 202.pdf` — проектные материалы
