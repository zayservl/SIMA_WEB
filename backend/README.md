# СИМА — Backend DEM Library

Вычислительная библиотека ЦМР/ЦММ/рельефа. Порт из legacy QGIS-плагина в чистый Python.
Без QGIS, PyQt5. С использованием GDAL, PDAL, rasterio, laspy, scipy, numpy, opencv.

## Структура — 4 пакета

```
backend/
├── packages/
│   ├── sima-dem-core/            # Фильтры, растры, обрезка, высоты, кривизна
│   │   └── src/sima_dem_core/
│   │       ├── check_classification.py
│   │       ├── crop.py
│   │       ├── curvature.py            # slope/aspect (gdal.DEMProcessing)
│   │       ├── height.py               # отметки высот (LAS ground / DEM grid)
│   │       ├── filters/                # 4 фильтра LAS: manual, stat, range, outlier
│   │       └── raster/                 # smooth (gauss), median, tpi (cv2.blur), vectorize, contours
│   ├── sima-dem-ground/         # ЦМР (GroundProcessing, SMRF, IDW, fillnodata)
│   │   └── src/sima_dem_ground/
│   │       └── ground.py               # SMRFConfig, FillConfig, RasterOutputConfig, GroundProcessing
│   ├── sima-dem-dsm/            # ЦММ (DSMBuilder, output_type=max)
│   │   └── src/sima_dem_dsm/
│   │       └── dsm.py                  # DSMConfig, DSMBuilder
│   └── sima-relief-service/     # Сервисный слой: оркестрация, статусы, сессии, оценка материалов
│       └── src/sima_relief_service/
│           ├── contract.py             # ReliefParams / ReliefRequest / DsmParams / SmrfParams / ...
│           ├── service.py              # ReliefService.run() — конвейер по тайлам с трекингом статусов
│           ├── steps.py               # step_crop / step_filter / step_dtm / step_dsm / step_smooth / ...
│           ├── assessment.py           # assess_materials — оценка ВЛС/АФС (СК, разрешение, плотность)
│           ├── status.py               # Job / Tile / TileStep / OutputArtifact
│           ├── storage.py              # Storage (LocalFS → S3) + Session
│           ├── determinism.py          # DeterminismContext (seed env vars)
│           ├── tin.py                  # TIN → DXF (scipy Delaunay)
│           └── shp_io.py               # OGR shapefile writer
├── tests/
│   ├── unit/                    # Unit-тесты (49 тестов)
│   ├── integration/             # Интеграционные тесты (8 тестов; часть требует test_data/, часть — синтетика)
│   └── conftest.py
├── relief_demo.ipynb            # Единый demo-ноутбук сервиса рельефа
├── run_dsm_demo.py              # Скрипт запуска ЦМР/ЦММ на двух датасетах
└── pyproject.toml
```

## Установка

### macOS (Homebrew)

```bash
brew install gdal pdal
cd backend
python3 -m venv .venv
source .venv/bin/activate
export PATH="/opt/homebrew/bin:$PATH"
pip install numpy scipy laspy rasterio shapely pyproj opencv-python
pip install gdal pdal
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-relief-service
pip install pytest pytest-cov
```

### Linux (apt/conda)

```bash
sudo apt install gdal-bin libgdal-dev pdal
conda create -n sima python=3.12
conda activate sima
conda install gdal pdal
pip install numpy scipy laspy rasterio shapely pyproj opencv-python
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-relief-service
```

## Запуск тестов

```bash
cd backend
pytest tests/ --no-cov -q          # без покрытия
pytest tests/ --cov --cov-report=term-missing  # с покрытием
```

## Demo-ноутбук

```bash
cd backend
jupyter notebook relief_demo.ipynb
```

Ноутбук поддерживает два датасета (`DATASET = 'demo'` или `'test'`) и выполняет полный
конвейер: оценка материалов → ЦМР → ЦММ → сглаживание → уклон/экспозиция/TPI →
горизонтали/отметки высот/TIN → визуализация → сравнение с эталоном.

## Сервис рельефа (sima-relief-service)

### Конвейер «Анализ рельефа» (Q3)

```
crop → filter → ЦМР (DTM) → ЦММ (DSM) → smooth → slope/aspect/TPI → contours/TIN → heights
```

### Параметры (ReliefParams)

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `target_crs` | str | "" | Целевая СК (Q3 «СК») |
| `filter_method` | str | "smrf" | Метод фильтрации: manual/stat/range/outlier/smrf |
| `smrf` | SmrfParams | defaults | SMRF: slope=0.2, window=16, threshold=0.45, scalar=1.2 |
| `smoothing` | SmoothingParams | disabled | Гаусс-сглаживание: sigma=2.0, order=0, window=5 |
| `dsm` | DsmParams | disabled | ЦММ (DSM): output_type=max, interpolate=True |
| `derivatives` | DerivativesParams | defaults | Уклон/экспозиция/TPI + интерполяция дырок |
| `vectors` | VectorsParams | defaults | Горизонтали [0.5, 2, 5, 10] м + TIN |
| `heights` | HeightsParams | disabled | Отметки высот: source=las, step=10 |
| `deterministic` | bool | False | Детерминизм (seed) |

### Выходные артефакты

| Артефакт | Формат | Q3 |
|---|---|---|
| ЦМР (DTM) | GeoTIFF (IDW) | ✅ |
| ЦММ (DSM) | GeoTIFF (max) | ✅ |
| Карта уклонов | GeoTIFF | ✅ |
| Карта экспозиции | GeoTIFF | ✅ |
| TPI | GeoTIFF | ✅ |
| Отметки высот | Shapefile | ✅ |
| Горизонтали | Shapefile (0.5/2/5/10 м) | ✅ |
| TIN | DXF | ✅ |

### API

```python
from sima_relief_service import (
    ReliefService, ReliefRequest, ReliefParams, TileInput,
    SmrfParams, SmoothingParams, DsmParams,
    DerivativesParams, VectorsParams, HeightsParams,
)

params = ReliefParams(
    target_crs="EPSG:32640",
    smoothing=SmoothingParams(enabled=True, sigma=2.0),
    dsm=DsmParams(enabled=True),
    derivatives=DerivativesParams(slopes=True, aspect=True, tpi=True),
    vectors=VectorsParams(horizontals=[0.5, 2.0, 5.0, 10.0], tin=True),
    heights=HeightsParams(enabled=True, source="las", step=10),
)
request = ReliefRequest(
    params=params, project_id="demo", resolution=1.0,
    tiles=[TileInput(name="pt000100", vls_path="input.las", afs_path="input.tif")],
)
svc = ReliefService(root_dir="output")
result = svc.run(request)
```

### Доступные параметры для интеграции

#### ReliefRequest (корневой запрос)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `params` | ReliefParams | — | Параметры расчёта (обязательное) |
| `tiles` | list[TileInput] | [] | Список пар тайлов для обработки |
| `project_id` | str | "default" | Идентификатор проекта |
| `season` | str \| None | None | Сезон съёмки (Q3) |
| `repository` | str \| None | None | Репозиторий сохранения (Q3, S3 prefix) |
| `resolution` | float | 1.0 | Разрешение ЦМР в метрах (Q3) |
| `session_id` | str \| None | None | Идентификатор сессии (для возобновления) |

#### TileInput (один тайл)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `name` | str | — | Имя тайла (обязательное) |
| `vls_path` | str \| None | None | Путь к LAS-файлу (ВЛС) |
| `afs_path` | str \| None | None | Путь к TIFF-файлу (АФС, для CRS) |
| `aoi` | str \| None | None | Путь к shapefile AOI (обрезка) |
| `existing_dtm` | str \| None | None | Существующая ЦМР (Q3 «Использование существующей ЦМР») |

#### ReliefParams (параметры расчёта)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `target_crs` | str | "" | Целевая СК (WKT или EPSG) |
| `filter_method` | str | "smrf" | Метод классификации рельефа |
| `filter` | FilterParams | defaults | Параметры фильтрации LAS |
| `smrf` | SmrfParams | defaults | Параметры SMRF |
| `smoothing` | SmoothingParams | disabled | Сглаживание ЦМР |
| `dsm` | DsmParams | disabled | Построение ЦММ (DSM) |
| `derivatives` | DerivativesParams | defaults | Производные: уклон/экспозиция/TPI + интерполяция |
| `vectors` | VectorsParams | defaults | Горизонтали + TIN |
| `heights` | HeightsParams | disabled | Отметки высот |
| `deterministic` | bool | False | Детерминизм (seed) |
| `seed` | int | 0 | Seed для детерминизма |

#### filter_method — классификация «Рельеф»

| Значение | Описание | Алгоритм |
|---|---|---|
| `"smrf"` | SMRF (по умолчанию) | PDAL `filters.smrf` внутри ground-классификации |
| `"manual"` | Ручная фильтрация | `filters.range` по Z[z_min:z_max] |
| `"stat"` | Статистическая | μ±mσ по Z (filters.stats + filters.range) |
| `"range"` | Перцентильная | min+%% диапазон Z (filters.stats + filters.range) |
| `"outlier"` / `"kmeans"` | Outlier removal | PDAL `filters.outlier` (statistical, mean_k, multiplier). `"kmeans"` — историческое имя значения в UI-контракте (`src/api/types.ts`), диспетчер `steps.py::step_filter` принимает оба как алиасы одного и того же фильтра. Неизвестный `filter_method` — `ValueError`, не тихий пропуск. |

#### SmrfParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `slope` | float | 0.2 | Наклон SMRF |
| `window` | int | 16 | Размер окна SMRF |
| `threshold` | float | 0.45 | Порог SMRF |
| `scalar` | float | 1.2 | Скаляр SMRF |
| `cut_smrf` | bool | False | Упрощённый SMRF (threshold=3 только) |
| `elm` | bool | True | Extended Local Minimum (всегда включён) |
| `outlier` | bool | True | Statistical outlier removal (всегда включён) |

#### FilterParams (для manual/stat/range/outlier)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `spm_min` | float \| None | None | Z_min для manual |
| `spm_max` | float \| None | None | Z_max для manual |
| `spr_num` | int \| None | None | m для stat (μ±mσ) |
| `spp_min` | float \| None | None | Мин. перцентиль для range (0-100, доля вычисляется в `contract.filter_kwargs`) |
| `spp_max` | float \| None | None | Макс. перцентиль для range (0-100, доля вычисляется в `contract.filter_kwargs`) |
| `mean_k` | int \| None | None | k соседей для outlier |
| `mult` | float \| None | None | Множитель σ для outlier / m для stat |

#### SmoothingParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `enabled` | bool | False | Включить сглаживание |
| `sigma` | float | 2.0 | σ гауссова фильтра (умножается на resolution) |
| `order` | int | 0 | Порядок гауссова фильтра (0 = сглаживание) |
| `window` | int | 5 | Размер окна (truncate = ((window-1)/2 - 0.5) / sigma) |

#### DsmParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `enabled` | bool | False | Включить построение ЦММ |
| `output_type` | str | "max" | Тип растеризации (max = верхняя поверхность) |
| `interpolate` | bool | True | Интерполяция дырок |
| `fill_holes` | bool | True | Заполнение внутренних дырок |
| `max_search_distance` | int | 100 | Макс. дистанция поиска для fillnodata |

#### DerivativesParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `slopes` | bool | False | Построить карту уклонов |
| `slopes_res` | float | 1.0 | Разрешение карты уклонов (м) |
| `aspect` | bool | False | Построить карту экспозиции |
| `aspect_res` | float | 1.0 | Разрешение карты экспозиции (м) |
| `tpi` | bool | False | Построить TPI |
| `tpi_radii` | list | [270, 810, 2430] | Радиусы TPI (м) |
| `interpolation` | bool | True | Интерполяция отсутствующих значений ЦМР |
| `inter_amp` | int | 100 | Макс. дистанция интерполяции (м) |

#### VectorsParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `horizontals` | list | [0.5, 2.0, 5.0, 10.0] | Шаги горизонталей (м) |
| `tin` | bool | False | Построить TIN-поверхность |

#### HeightsParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `enabled` | bool | False | Включить отметки высот |
| `source` | str | "las" | Источник: "las" (облако точек) или "dem" (растр ЦМР) |
| `step` | int | 10 | Каждая n-я точка ground (для source=las) |

## Ключевые алгоритмические решения

1. **Без экстраполяции краёв** — `fillnodata` заполняет только внутренние дырки (полностью окружённые валидными данными, `scipy.ndimage.binary_fill_holes`). Краевые nodata остаются. Реализовано одинаково в DTM (`ground.py`), сглаживании (`smooth.py`) и DSM (`dsm.py`).

2. **Min-Z fallback из ground-точек** — дырки DTM заполняются минимальными Z из ground-классифицированных точек (не из всех точек).

3. **Склоны по сглаженной DTM** — уклоны и экспозиции строятся по сглаженной DTM, не по сырой.

4. **IDW растеризация** — DTM строится через PDAL `writers.gdal` с `output_type="idw"`.

5. **DSM (ЦММ) через max** — `output_type="max"` берёт максимальную Z по всем точкам в ячейке (после `filters.elm`/`filters.outlier`/`filters.range(Classification[1:5])`/`filters.sample`). Классы 1-5 (unclassified/ground/low-med-high vegetation); строения (класс 6) и прочие классы в ЦММ не попадают — не настраивается через `DSMConfig`, это осознанное отличие от «первой поверхности» ASPRS/ISO-определения DSM, ориентированное на растительность.

6. **TPI трёхмасштабный** — радиусы 270/810/2430 м, `cv2.blur` box filter, нормировка на std. Радиус трактуется как полный размер окна `cv2.blur` (не диаметр/радиус в классическом смысле) — фактический охват вдвое меньше номинального.

7. **Пропуск тайла при ошибке** — упавший тайл → status "failed" + reason, остальные продолжаются.

8. **elm/outlier до финального отбора Classification==2** — и для уже классифицированных LAS (`_build_save_ground_pipeline`), и для сырых (`_build_ground_pipeline`) шумовые точки помечаются классом 7 через `filters.elm`/`filters.outlier` **до** финального `filters.range(Classification[2:2])`, иначе помеченный шум не отсеивается перед растеризацией.

## Известные отклонения от стандартов / открытые вопросы

Зафиксированы аудитом; не баги, но требуют явного продуктового решения перед релизом библиотеки:

- **slope/aspect теряют внешний пиксель растра** — `gdal.DEMProcessing(...)` вызывается без `computeEdges=True`, поэтому крайняя строка/столбец уклона и экспозиции — nodata, даже если исходная ЦМР там валидна (`sima_dem_core/curvature.py`). Важно для бесшовной мозаики тайлов.
- **SMRF использует все типы возвратов** (`SMRFConfig.returns` по умолчанию `first/last/intermediate/only`), а не `last,only`, как рекомендует Pingel et al. 2013 — включение первых/промежуточных возвратов (чаще не-грунтовых в растительности) в SMRF отклоняется от типовой практики.
- **CRS не валидируется** между AOI/LAS/DEM в нескольких местах (`ground.py::_maybe_crop_stage`, `crop.py::Crop.cropCalc`, `height.py`) — риск тихого рассинхрона систем координат при прямом использовании библиотеки вне сервисного слоя.
- **Децимация отметок высот из LAS** (`height.py::_heights_from_las`, `step`-й по счёту точка) идёт по порядку точек в файле (обычно порядок сканирования, не пространственный) — не гарантирует равномерного распределения по площади, в отличие от `_heights_from_dem` (растровый шаг, корректно равномерный).
- **`determinism.py`** выставляет `PYTHONHASHSEED` в `os.environ` уже во время выполнения процесса — эффекта на текущий интерпретатор это не даёт; в проверенном коде не найдено шагов со случайностью, которые seed реально бы фиксировал.
- **`crop.py`** обрезка AOI — точечный `shapely.contains()` в цикле на чистом Python; не рассчитан на объёмы реального LiDAR (10-100M точек), для продуктизации потребует векторизации/пространственного индекса.
- **Метаданные пакетов** — во всех `pyproject.toml` (4 пакета) отсутствуют `license`/`authors`/`classifiers`, версии `gdal`/`pdal` не закреплены (в отличие от numpy/scipy).

## Тестовые данные

Интеграционные тесты требуют:
- `test_data/P-42-041-239-g_ground_TLO.las` — нормализованный LAS (TLO)
- `test_data/P-42-041-239-g_DSM.tif` — эталонный DSM
- `test_data/P-42-041-239-g.tif` — АФС

Demo-датасет:
- `23_04_12_digital_elevation_1-46-315/demo_data/pt000100.las`
- `23_04_12_digital_elevation_1-46-315/demo_data/00000100.tif`

## Тесты

57 тестов, 0 неудач (56 исходных + `TestSyntheticDSMBuilderConvergence` —
синтетический численный тест сходимости DSMBuilder к аналитической
поверхности, ранее отсутствовавший: `test_dsm_convergence.py` и
`test_synthetic_dsm.py`, несмотря на название, проверяли только
GroundProcessing/DTM). Покрытие с test_data/ — 80%. Слабое покрытие: `filters/outlier_filter.py` (43%),
`raster/vectorize.py` (54%), `steps.py` (52%).

## Зависимости

| Пакет | Назначение |
|-------|-----------|
| GDAL | Геопространственная обработка (DEMProcessing, ContourGenerate, Warp) |
| PDAL | Обработка облаков точек (SMRF, elm, outlier, sample, hag_delaunay) |
| laspy | Чтение/запись LAS |
| rasterio | Чтение/запись GeoTIFF, fillnodata |
| scipy | gaussian_filter, binary_fill_holes, Delaunay |
| numpy | Массивы |
| opencv-python | cv2.blur (TPI box filter) |
| shapely | Геометрия (crop AOI) |
| pyproj | Координатные системы |