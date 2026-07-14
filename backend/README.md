# СИМА — Backend DEM Library

Вычислительная библиотека ЦМР/ЦМД/рельефа. Порт из legacy QGIS-плагина в чистый Python.
Без QGIS, PyQt5. С использованием GDAL, PDAL, rasterio, laspy, scipy, numpy.

## Структура — 4 отдельных устанавливаемых пакета

```
backend/
├── packages/
│   ├── sima-dem-core/          # Фильтры, растры, обрезка, высоты, кривизна
│   │   └── src/sima_dem_core/
│   │       ├── check_classification.py
│   │       ├── crop.py
│   │       ├── curvature.py          # slope/aspect
│   │       ├── height.py             # отметки высот
│   │       ├── filters/              # 4 фильтра LAS
│   │       └── raster/               # smooth, median, tpi, vectorize
│   ├── sima-dem-ground/        # ЦМР (GroundProcessing, SMRF)
│   │   └── src/sima_dem_ground/
│   │       └── ground.py             # SMRFConfig, FillConfig, GroundProcessing
│   ├── sima-dem-dsm/           # ЦМД (DSMBuilder)
│   │   └── src/sima_dem_dsm/
│   │       └── dsm.py                # DSMConfig, DSMBuilder
│   └── sima-dem-pipeline/     # Оркестрация
│       └── src/sima_dem_pipeline/
│           └── pipeline.py          # PipelineConfig, ReliefPipeline
├── tests/
│   ├── unit/                  # 34 unit-теста
│   ├── integration/           # 7 интеграционных тестов
│   └── conftest.py
├── run_dsm_demo.py            # Скрипт запуска на двух датасетах
├── sima_dsm_demo.ipynb        # Jupyter notebook для интерактивного расчёта
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
pip install numpy scipy laspy rasterio shapely pyproj
pip install gdal pdal
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-dem-pipeline
pip install pytest pytest-cov
```

### Linux (apt/conda)

```bash
sudo apt install gdal-bin libgdal-dev pdal
conda create -n sima python=3.12
conda activate sima
conda install gdal pdal
pip install numpy scipy laspy rasterio shapely pyproj
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-dem-pipeline
```

## Запуск тестов

```bash
cd backend
pytest tests/ --cov --cov-report=term-missing
```

## Интерактивный запуск (Jupyter)

```bash
cd backend
jupyter notebook sima_dsm_demo.ipynb
```

В ячейке 2 задать `DATASET = 'demo'` или `'test'` и параметры расчёта.

## Скрипт запуска на двух датасетах

```bash
cd backend
source .venv/bin/activate
export PATH="/opt/homebrew/bin:$PATH"
python run_dsm_demo.py
```

## API — инкапсулированные параметры

Все параметры в dataclass-конфигах, без хардкода:

```python
from sima_dem_ground.ground import GroundProcessing, SMRFConfig, FillConfig
from sima_dem_dsm.dsm import DSMBuilder, DSMConfig
from sima_dem_core.raster.tpi import TPIConfig

# ЦМР (DTM)
gp = GroundProcessing(
    output="/tmp/output",
    resolution=1.0,
    crs="EPSG:32642",
    interpolate=True,
    smrf=SMRFConfig(slope=0.2, window=16, threshold=0.45, scalar=1.2),
    fill=FillConfig(fill_holes=True, max_search_distance=100),
)
gp.get_raster("input.las", crs_wkt="EPSG:32642")

# ЦМД (DSM)
builder = DSMBuilder(
    output="/tmp/output",
    crs="EPSG:32642",
    config=DSMConfig(resolution=1.0, output_type="max", interpolate=True, fill_holes=True),
)
dsm_path = builder.build("input.las")
```

## Ключевые алгоритмические решения

1. **Без экстраполяции краёв** — `fillnodata` заполняет только внутренние дырки (nodata, окружённые валидными данными). Краевые nodata остаются.

2. **Интерполяция дырок при сглаживании** — `gauss_smooth` заполняет внутренние дырки перед фильтром, заменяет оставшийся nodata на медиану валидных, затем восстанавливает nodata на краях.

3. **Склоны по сглаженной DTM** — уклоны и экспозиции строятся по сглаженной DTM (`*_dem_smooth.tif`), не по сырой.

4. **CRS из эталонного TIFF** — CRS извлекается из эталонного DSM или АФС, не хардкодится (SK42 ≠ EPSG:32642).

## Тестовые данные

Интеграционный тест требует:
- `test_data/P-42-041-239-g_ground_TLO.las` — нормализованный LAS
- `test_data/P-42-041-239-g_DSM.tif` — эталонный DSM

Синтетический тест (`test_synthetic_dsm.py`) не требует внешних данных.

## Покрытие

41 тест, 0 неудач, покрытие **82%** (требование ≥75%).

## Зависимости

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| GDAL | 3.13.1 | Геопространственная обработка |
| PDAL | 3.5.4 | Обработка облаков точек (SMRF) |
| laspy | 2.7.0 | Чтение/запись LAS |
| rasterio | 1.5.0 | Чтение/запись GeoTIFF |
| scipy | 1.18.0 | Фильтры, интерполяция |
| numpy | 2.5.1 | Массивы |
| shapely | 2.1.2 | Геометрия |
| pyproj | 3.7.2 | Координатные системы |