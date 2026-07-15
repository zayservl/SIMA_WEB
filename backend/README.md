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
│   ├── unit/                    # Unit-тесты (56 тестов)
│   ├── integration/             # Интеграционные тесты (требуют test_data/)
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

## Ключевые алгоритмические решения

1. **Без экстраполяции краёв** — `fillnodata` заполняет только внутренние дырки. Краевые nodata остаются.

2. **Min-Z fallback из ground-точек** — дырки DTM заполняются минимальными Z из ground-классифицированных точек (не из всех точек).

3. **Склоны по сглаженной DTM** — уклоны и экспозиции строятся по сглаженной DTM, не по сырой.

4. **IDW растеризация** — DTM строится через PDAL `writers.gdal` с `output_type="idw"`.

5. **DSM (ЦММ) через max** — `output_type="max"` берёт максимальную Z по всем точкам в ячейке.

6. **TPI трёхмасштабный** — радиусы 270/810/2430 м, `cv2.blur` box filter, нормировка на std.

7. **Пропуск тайла при ошибке** — упавший тайл → status "failed" + reason, остальные продолжаются.

## Тестовые данные

Интеграционные тесты требуют:
- `test_data/P-42-041-239-g_ground_TLO.las` — нормализованный LAS (TLO)
- `test_data/P-42-041-239-g_DSM.tif` — эталонный DSM
- `test_data/P-42-041-239-g.tif` — АФС

Demo-датасет:
- `23_04_12_digital_elevation_1-46-315/demo_data/pt000100.las`
- `23_04_12_digital_elevation_1-46-315/demo_data/00000100.tif`

## Тесты

56 тестов, 0 неудач. Покрытие unit-тестами — без интеграционных данных ~22%; с test_data/ — выше.

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