# СИМА — Backend DEM Library

Вычислительная библиотека ЦМР/ЦМД/рельефа. Порт из legacy QGIS-плагина в чистый Python.

## Структура

```
backend/
├── sima_dem/           # Вычислительные модули
│   ├── ground.py        # ЦМР (SMRF + интерполяция) — отдельный модуль
│   ├── dsm.py           # DSM (writers.gdal max) — отдельный модуль
│   ├── curvature.py     # Уклоны/экспозиции
│   ├── crop.py           # Обрезка LAS по AOI
│   ├── height.py         # Отметки высот
│   ├── pipeline.py       # Оркестрация конвейера
│   ├── check_classification.py
│   ├── filters/          # 4 фильтра LAS-точек
│   │   ├── manual_filter.py
│   │   ├── stat_filter.py
│   │   ├── range_filter.py
│   │   └── outlier_filter.py
│   └── raster/           # Утилиты растров
│       ├── smooth.py     # Гаусс-сглаживание
│       ├── median.py     # Медианный фильтр
│       ├── tpi.py        # TPI (индекс топографического положения)
│       └── vectorize.py  # Бинаризация/векторизация
├── tests/
│   ├── unit/            # 34 unit-теста
│   ├── integration/     # 7 интеграционных тестов (синтетический + реальный DSM)
│   ├── fixtures/        # Утилиты для тестовых данных
│   └── conftest.py
└── pyproject.toml
```

## Установка

### macOS (Homebrew)

```bash
brew install gdal pdal
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install numpy scipy laspy rasterio shapely pyproj
pip install gdal pdal
pip install -e ".[test]"
```

### Linux (apt/conda)

```bash
sudo apt install gdal-bin libgdal-dev pdal
conda create -n sima python=3.12
conda activate sima
conda install gdal pdal
pip install numpy scipy laspy rasterio shapely pyproj
pip install -e ".[test]"
```

## Запуск тестов

```bash
cd backend
pytest tests/ --cov=sima_dem --cov-report=term-missing
```

## Тестовые данные

Интеграционный тест `test_dsm_convergence.py` требует:
- `test_data/P-42-041-239-g_ground_TLO.las` — нормализованный LAS
- `test_data/P-42-041-239-g_DSM.tif` — эталонный DSM

Если тестовые данные отсутствуют, тест пропускается.

Синтетический тест `test_synthetic_dsm.py` не требует внешних данных — он создаёт LAS с известным параболоидом Z=100+0.001*(x²+y²) и проверяет сходимость.

## Покрытие

Текущее покрытие: **78.51%** (требование ≥75%).

## Зависимости

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| GDAL | 3.13.1 | Геопространственная обработка |
| PDAL | 3.5.4 | Обработка облаков точек |
| laspy | 2.7.0 | Чтение/запись LAS |
| rasterio | 1.5.0 | Чтение/запись GeoTIFF |
| scipy | 1.18.0 | Фильтры, интерполяция |
| numpy | 2.5.1 | Массивы |
| shapely | 2.1.2 | Геометрия |
| pyproj | 3.7.2 | Координатные системы |