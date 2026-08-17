# СИМА — Backend DEM Library

Вычислительная библиотека ЦМР/ЦММ/рельефа. Порт из legacy QGIS-плагина в чистый Python.
Без QGIS, PyQt5. С использованием GDAL, PDAL, rasterio, laspy, scipy, numpy, opencv.

## Структура — 5 пакетов

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
│   │       └── raster/                 # holes (заполнение пустот), hydro (гидровыравнивание),
│   │                                   # smooth (gauss), median, tpi (cv2.blur), vectorize, contours
│   ├── sima-dem-ground/         # ЦМР (GroundProcessing, SMRF, IDW, fillnodata)
│   │   └── src/sima_dem_ground/
│   │       └── ground.py               # SMRFConfig, FillConfig, RasterOutputConfig, GroundProcessing
│   ├── sima-dem-dsm/            # ЦММ (DSMBuilder, output_type=max)
│   │   └── src/sima_dem_dsm/
│   │       └── dsm.py                  # DSMConfig, DSMBuilder
│   ├── sima-forest-cmd/         # ЦМД: древостой — растр полога, деревья, кроны
│   │   └── src/sima_forest_cmd/
│   │       ├── chm.py                  # CHMConfig, CHMBuilder (hag_delaunay → max)
│   │       ├── treetops.py             # детекция вершин, высота дерева
│   │       ├── crowns.py               # водораздел крон, полигоны, площади
│   │       ├── afs.py                  # отсев и уточнение вершин по снимку
│   │       ├── cost.py                 # поверхность стоимости для водораздела
│   │       ├── features.py             # признаки крон: геометрия, высоты, сигнал ВЛС
│   │       ├── agreement.py            # IoU с эталонным набором крон
│   │       ├── diameter.py             # диаметр ствола — интерфейс, алгоритм не реализован
│   │       └── vector_io.py            # запись деревьев и крон в shapefile
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
│   ├── unit/                    # Unit-тесты (229 тестов)
│   ├── integration/             # Интеграционные тесты (8 тестов; часть требует test_data/, часть — синтетика)
│   └── conftest.py
├── relief_demo.ipynb            # Единый demo-ноутбук сервиса рельефа
├── forest_s3_yuilskiy.ipynb     # ЦМД и деревья на Юильском: сверка с эталоном СИМА 1.44
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
pip install numpy scipy laspy rasterio shapely pyproj opencv-python scikit-image
pip install gdal pdal
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-forest-cmd
pip install -e packages/sima-relief-service
pip install pytest pytest-cov
```

### Linux (apt/conda)

```bash
sudo apt install gdal-bin libgdal-dev pdal
conda create -n sima python=3.12
conda activate sima
conda install gdal pdal
pip install numpy scipy laspy rasterio shapely pyproj opencv-python scikit-image
pip install -e packages/sima-dem-core
pip install -e packages/sima-dem-ground
pip install -e packages/sima-dem-dsm
pip install -e packages/sima-forest-cmd
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

## Параметры библиотеки (прямое использование, без сервисного слоя)

Пакеты `sima-dem-core`, `sima-dem-ground` и `sima-dem-dsm` работают самостоятельно.
Сервис их только оркеструет и своих значений по умолчанию не подставляет — всё
ниже действует и при прямом вызове.

### SMRFConfig — классификация ground (`sima_dem_ground`)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `slope` | float | 0.2 | Наклон SMRF |
| `window` | int | 16 | Размер окна SMRF |
| `threshold` | float | 0.45 | Порог SMRF |
| `scalar` | float | 1.2 | Скаляр SMRF |
| `returns` | list | first/last/intermediate/only | Учитываемые типы возвратов (отклонение от Pingel et al. 2013 — см. «Известные отклонения») |

### FillConfig — заполнение пустот ЦМР (`sima_dem_ground`)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `fill_holes` | bool | True | Включить заполнение пустот |
| `max_search_distance` | int | 100 | Радиус поиска для `fill_method="idw"`, px |
| `smoothing_iterations` | int | 0 | Сглаживание заполненных значений внутри `GDALFillNodata` (только для `"idw"`) |
| `fallback_to_min_z` | bool | True | Добивать пустоты минимальным Z из ground-точек до интерполяции |
| `fill_method` | str | "laplace" | Метод интерполяции: `"laplace"` (гармоническая, без лучей) или `"idw"` (`GDALFillNodata`) |
| `fill_passes` | int | 3 | Проходов заполнения; `1` — однопроходное поведение |
| `hydro_flatten` | bool | True | Выравнивать пустоты-водоёмы плоской отметкой (3DEP) |
| `edge_extrapolation_m` | float | 5.0 | Допустимая экстраполяция за границу данных, м; `0` — только внутренние дыры |

### RasterOutputConfig — растеризация ЦМР (`sima_dem_ground`)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `output_type` | str | "idw" | Тип растеризации PDAL `writers.gdal` |
| `data_type` | str | "float32" | Тип данных выходного GeoTIFF |
| `gdaldriver` | str | "GTiff" | Драйвер GDAL |

### DSMConfig — построение ЦММ (`sima_dem_dsm`)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `resolution` | float | 1.0 | Разрешение растра, м |
| `output_type` | str | "max" | Тип растеризации (max — верхняя поверхность) |
| `data_type` | str | "float32" | Тип данных выходного GeoTIFF |
| `gdaldriver` | str | "GTiff" | Драйвер GDAL |
| `interpolate` | bool | True | Запускать заполнение пустот после растеризации |
| `fill_holes` | bool | True | Включить заполнение пустот |
| `max_search_distance` | int | 100 | Радиус поиска для `fill_method="idw"`, px |
| `smoothing_iterations` | int | 0 | Сглаживание заполненных значений (только для `"idw"`) |
| `fill_method` | str | "laplace" | Метод интерполяции пустот |
| `fill_passes` | int | 3 | Проходов заполнения |
| `hydro_flatten` | bool | True | Гидровыравнивание водоёмов |
| `edge_extrapolation_m` | float | 5.0 | Допустимая экстраполяция за границу данных, м |

### Растровые операции (`sima_dem_core.raster`)

`fill_voids(array, valid, ...) -> VoidFill` — заполнение пустот; возвращает растр,
маску заполненных ячеек, маску гидровыравненных и их отметки.

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `method` | str | "laplace" | `"laplace"` — решение уравнения Лапласа в пустоте; `"idw"` — `GDALFillNodata` |
| `max_search_distance` | int | 100 | Радиус поиска для `"idw"`, px |
| `smoothing_iterations` | int | 0 | Сглаживание заполненных значений для `"idw"` |
| `max_extrapolation_px` | float | 0.0 | Допустимая экстраполяция за границу данных, px (см. `px_from_metres`) |
| `max_passes` | int | 3 | Максимум проходов |
| `resolution_m` | float | 1.0 | Размер ячейки, м — нужен для порога площади водоёма |
| `hydro_flatten` | bool | False | Включить гидровыравнивание водоёмов |
| `min_water_area_m2` | float \| None | None | Порог площади водоёма; `None` — порог 3DEP (8000 м²) |
| `water` | ndarray \| None | None | Готовая маска водоёмов; отменяет отбор по площади |

`flatten_water_voids(array, valid, voids, resolution_m, ...) -> WaterFlattening` —
гидровыравнивание (см. `raster/hydro.py`).

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `water` | ndarray \| None | None | Готовая маска водоёмов (брейклайны, слой анализа воды) |
| `min_area_m2` | float | 8000.0 | Минимальная площадь водоёма — порог 3DEP (0.8 га) |
| `rim_quantile` | float | 0.05 | Квантиль окаймления, дающий отметку воды |

`fillable_mask(valid, max_extrapolation_px=0.0)` — маска ячеек под заполнение.
`px_from_metres(distance_m, resolution_m)` — перевод расстояния `distance_m` (м) в
пиксели растра при разрешении `resolution_m`.

`gauss_smooth(raster, smoothed, sigma, order, window_size, ...)` — гауссово сглаживание.

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `sigma` | float | — | σ гауссова фильтра (в сервисе умножается на разрешение) |
| `order` | int | — | Порядок фильтра; `0` — сглаживание |
| `window_size` | int | — | Размер окна; задаёт `truncate = ((window_size-1)/2 - 0.5) / sigma` |
| `fill_holes` | bool | False | Заполнить пустоты перед сглаживанием |
| `max_search_distance` | int | 100 | Радиус поиска для `"idw"`, px |
| `max_extrapolation_px` | float | 0.0 | Допустимая экстраполяция за границу данных, px |
| `fill_passes` | int | 3 | Проходов заполнения |
| `fill_method` | str | "laplace" | Метод интерполяции пустот |

## ЦМД — древостой (sima-forest-cmd)

### Конвейер

```
облако → ЦМД (растр полога) → вершины деревьев → кроны → [корректировка по АФС] → shapefile
```

ЦМД строится отдельным проходом PDAL по облаку: `filters.hag_delaunay` считает
превышение точки над триангулированной поверхностью земли, `Z` заменяется этим
превышением, результат растеризуется максимумом в ячейке. Нормализация выполняется
внутри модуля, поэтому **абсолютный уровень высот безразличен**: облако в ТЛО
(нормализованные высоты) и облако в абсолютных отметках дают один результат. ЦМД
не строится вычитанием ЦМР из ЦММ и наличия этих растров не требует — этим она
отличается от ЦМР, которая на ТЛО вырождается в константу.

### Сходимость с легаси

На 12 тайлах Юильского при параметрах СИМА 1.44 (0.5 м, окно 1 м, медиана 1 px)
найдено 256 804 дерева против 266 753 в эталоне — медиана отношения **0.969×**
(диапазон 0.950…1.030), расхождение медианной высоты дерева 0.04 м.
Прогон и сверка — в `forest_s3_yuilskiy.ipynb`.

### Разрешение решает

Окно поиска задаётся в метрах, но переводится в целое число пикселей, поэтому его
фактический поперечник равен `2 · radius_px · res + res` и зависит от сетки:

| Разрешение ЦМД | радиус окна | фактическое окно | найдено деревьев |
|---|---|---|---|
| 0.5 м | 2 px | 2.5 м | 256 804 (0.97× эталона) |
| 1.0 м | 1 px | 3.0 м | 164 648 (0.62× эталона) |

Переход на метровую сетку теряет **35.9 %** деревьев: окно физически шире, а
соседние кроны на грубой сетке сливаются в один максимум.

### CHMConfig — построение растра ЦМД

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `resolution` | float | 0.5 | Разрешение растра, м |
| `output_type` | str | "max" | Тип растеризации (max — верхняя точка полога) |
| `data_type` | str | "float32" | Тип данных выходного GeoTIFF |
| `gdaldriver` | str | "GTiff" | Драйвер GDAL |
| `interpolate` | bool | True | Запускать заполнение пустот после растеризации |
| `fill_holes` | bool | True | Включить заполнение пустот |
| `fill_method` | str | "laplace" | Метод интерполяции пустот (см. `holes.fill_voids`) |
| `fill_passes` | int | 3 | Проходов заполнения |
| `max_search_distance` | int | 100 | Радиус поиска для `fill_method="idw"`, px |
| `edge_extrapolation_m` | float | 0.0 | Экстраполяция за границу данных, м |
| `smooth` | bool | False | Гауссово сглаживание полога после заполнения пустот |
| `smooth_sigma` | float | 1.0 | σ гауссова фильтра; умножается на `resolution` |
| `smooth_order` | int | 0 | Порядок производной гауссианы; 0 — обычное сглаживание |
| `smooth_window` | int | 3 | Размер окна, задаёт усечение ядра (`truncate`) |
| `with_intensity` | bool | False | Дополнительный растр интенсивности (mean) |
| `with_density` | bool | False | Дополнительный растр плотности (`nndistance`, mean) |
| `save_classified_las` | bool | False | Сохранить облако с переклассифицированной растительностью |
| `low_vegetation_max_m` | float | 0.5 | Верхняя граница класса 3 (подлесок), м |
| `medium_vegetation_max_m` | float | 5.0 | Верхняя граница класса 4 (молодняк), м |

Гидровыравнивание при заполнении пустот ЦМД не применяется: на растре высот над
землёй вода и так близка к нулю.

Сглаживание использует тот же `sima_dem_core.raster.smooth.gauss_smooth`, что и
ЦМР, с той же семантикой параметров. Исходный растр не заменяется: сглаженный
пишется рядом как `<stem>_chm_smooth.tif` и возвращается в `CHMResult.chm_smooth`.
Медианное сглаживание в `prepare_chm` (радиус `smooth_radius_px`) — отдельная
операция: она нужна только внутри детекции вершин и на выходной растр не влияет.

### Детекция вершин (`treetops`)

`detect_tree_tops(chm, resolution_m, window_m, ...) -> TreeTops` — локальные
максимумы полога; слипшиеся в плато ячейки одной вершины схлопываются в одну точку
по центру масс.

| Параметр | Тип | Default | Описание |
|---|---|---|---|
| `window_m` | float | — | Окно поиска вершин, м — радиус ядра до перевода в пиксели |
| `min_height_m` | float | 0.5 | Минимальная высота дерева, м |
| `max_height_m` | float | 60.0 | Верхняя отсечка высоты — выше считается шумом ЦМД, м |
| `smooth_radius_px` | int | 1 | Радиус медианного сглаживания перед поиском, px |
| `prepared` | bool | False | Растр уже прошёл `prepare_chm` |
| `height_from_smoothed` | bool | False | Снимать высоту со сглаженного растра (поведение легаси) |

Высота по умолчанию снимается с **несглаженного** растра: медианный фильтр срезает
макушки и занижает высоту тем сильнее, чем острее крона (на синтетической кроне
23 м сглаживание радиусом 1 px даёт 21.8 м). Сглаживание нужно, чтобы не ловить
ложные вершины на шуме, но мерить по нему высоту значит занижать весь древостой.

Вспомогательные: `window_radius_px(window_m, resolution_m)` — перевод окна в радиус
в пикселях с округлением (усечение обнуляло бы окно, равное разрешению);
`prepare_chm(chm, ...)` — сглаживание и отсечки; `to_world(tops, transform, offset)` —
перевод вершин в СК; `split_by_height(heights, shrub_height_m=5.0)` — разделение на
древостой и кустарник; `disc_kernel(radius_px)` — дисковое ядро.

### Кроны (`crowns`)

`delineate_crowns(chm, tops, min_height_m=0.5, surface=None)` — водораздел по
инвертированному пологу от маркеров-вершин; заливка ограничена маской полога,
поэтому в просветы и на землю не уходит. Каждой вершине соответствует ровно одна
зона. `surface` — готовая поверхность стоимости (см. ниже); `None` — заливка по
`−CHM`, то есть только по высоте.

`crowns_to_polygons(labels, transform, resolution_m=1.0)` — векторизация меток;
площадь считается по геометрии полигона за вычетом отверстий (просветы полога
внутри кроны не заполняются). Крона из нескольких несвязных кусков даёт несколько
полигонов с одним `tree_index`.

`crown_areas_by_tree(labels, n_trees, resolution_m)` — площадь кроны на каждое
дерево, м²; для вершин без кроны — 0.

### Корректировка по АФС (`afs`) — необязательна

**ЦМД, вершины и кроны считаются по одному только ВЛС.** АФС в расчёт не входит:
`CHMBuilder` читает LAS, `detect_tree_tops` и `delineate_crowns` работают с массивом
растра. Модуль `afs` — отдельный, вызывается по желанию; без него код идёт тем же
путём. Сходимость 0.969× с эталоном получена именно так — прогон шёл с
`AFS_CORRECTION = False`, ни один пиксель снимка в расчёт не попал.

Минимальный сценарий «только ВЛС»:

```python
from sima_forest_cmd import (CHMBuilder, CHMConfig, read_chm,
                             detect_tree_tops, delineate_crowns, crowns_to_polygons)

result = CHMBuilder(output='out', crs='').build('cloud.las')
chm, transform, res = read_chm(result.chm)
tops = detect_tree_tops(chm, resolution_m=res, window_m=1.0)
crowns = crowns_to_polygons(delineate_crowns(chm, tops), transform)
```

`crs=''` допустимо: параметр `override_srs` тогда не передаётся в PDAL и СК берётся
из самого LAS. Задавать её явно нужно только если в облаке СК нет — снимок для
этого не обязателен, подойдёт любой источник WKT.

Когда снимок всё же есть, корректировка убирает ложные вершины и уточняет положение
стволов. Съёмка ведётся в видимом диапазоне, канала ближнего ИК нет, поэтому NDVI
неприменим и маска строится по RGB-индексам: `ExG` (2g − r − b по нормированным
каналам) или `VARI`.

| Функция | Назначение |
|---|---|
| `vegetation_index(rgb, method)` | Индекс: `method` — `"exg"` или `"vari"` |
| `vegetation_mask(rgb, method, threshold, min_area_px)` | Маска растительности; `min_area_px` убирает мелкие пятна |
| `resample_mask_to_grid(mask, shape)` | Приведение маски снимка к сетке ЦМД |
| `correct_tops(rows, cols, veg_mask, resolution_m, ...)` | Отсев и уточнение вершин |

`correct_tops` принимает `drop_non_vegetation` (отсев вершин вне растительности),
`refine_position` (сдвиг к центру кроны) и `refine_radius_m` (максимальный сдвиг,
по умолчанию 1.5 м; дальний сдвиг означает слитный полог, и положение по ЦМД
надёжнее). Возвращает `TopsCorrection` со статистикой: сколько отсеяно, сколько
сдвинуто и на сколько.

### Поверхность стоимости водораздела (`cost`)

Заливка по `−CHM` знает только высоту, и там, где кроны одинаковой высоты
соприкасаются, седловины нет — граница ставится равноудалённо от вершин.
`build_cost_surface` складывает нормированные карты границ из разных источников:

```
surface = w_height·norm(−CHM) + w_chm_gradient·norm(|∇CHM|)
        + w_afs_edges·norm(|∇I|) + w_afs_texture·norm(σ_local(I))
        + w_intensity·norm(|∇ITS|) + w_density·norm(|∇DEN|)
```

`CostWeights` — веса компонент; по умолчанию `height=1`, остальные нули, что даёт
**побитово тот же** растр меток, что и заливка по `−CHM` (зафиксировано тестом).
Высота нормируется без обрезки, карты границ — робастно по p1–p99: обрезка нужна,
чтобы одиночный выброс градиента не подавил остальные слагаемые, но для высоты она
склеила бы макушки высоких крон в плато.

| Параметр `build_cost_surface` | Тип | Default | Описание |
|---|---|---|---|
| `weights` | CostWeights | height=1 | Веса компонент |
| `afs_rgb` | ndarray \| None | None | Снимок (3,H,W) или (H,W,3) в своей сетке |
| `intensity` | ndarray \| None | None | Растр интенсивности (ITS) |
| `density` | ndarray \| None | None | Растр плотности точек (DEN) |
| `canopy_mask` | ndarray \| None | None | Где нормировать компоненты |
| `texture_window` | int | 3 | Окно локального СКО для текстуры, px |

Вес на компоненту без данных — `ValueError`, а не молчаливое обнуление.
Вспомогательные: `robust_normalize`, `gradient_magnitude`, `local_std`, `luminance`.

**Измеренный результат: на Юильском при 0.5 м снимок сегментацию не улучшает.**
Согласие с СИМА 1.44 падает с 0.576 (только высота) до 0.358 (границы АФС), и
независимый от эталона показатель говорит о том же: доля крон крупнее 50 м² растёт
с 0.001 % до 0.093 %, медиана площади падает с 4.0 до 3.3 м². Причина в исходной
посылке — слипания крон там нет: медианная крона 3.8 м², то есть круг поперечником
2.2 м. Дополнительные границы режут и без того мелкие кроны по теням и шуму снимка.
Механизм проверен на синтетике и работает; смысл он имеет на крупных слипшихся
кронах, где его и надо перемерить. Подробности — в `forest_s3_yuilskiy.ipynb`, п. 11.

### Признаки крон (`features`)

`crown_features(labels, chm, transform, resolution_m, ...) -> CrownFeatures` —
таблица по одной строке на дерево. Точки облака привязываются к кронам через растр
меток (координата → `labels[row, col]`), а не пространственным соединением: один
проход по массиву вместо `sjoin` и без geopandas в зависимостях.

| Группа | Признаки |
|---|---|
| Геометрия | `area_m2`, `perimeter_m`, `equivalent_diameter_m`, `compactness`, `apex_offset_m`, `n_cells` |
| Структура высот | `chm_mean_m`, `chm_std_m`, `chm_p50…p95_m`, `chm_p99_m`, `height_robust_m`, `chm_max_m` |
| Сигнал ВЛС | `n_points`, `point_density_m2`, `z_mean_m`, `z_std_m`, `z_p50…p95_m`, `vci`, `intensity_mean/std`, `intensity_p50…p95`, `first_return_share`, `multi_return_share` |

Высота дерева даётся тремя оценками: `chm_max_m` воспроизводит легаси и принимает
любой выброс за макушку; `chm_p99_m` устойчив только на крупных кронах — на 36
ячейках он отстоит от максимума на 3 %; `height_robust_m` отбрасывает долю
`height_trim` (по умолчанию 5 %, но не менее одной) самых высоких ячеек и работает
при любом размере кроны, что и требуется при медиане в 15–20 ячеек.

Периметр считается по рёбрам между ячейками разных меток, поэтому для ступенчатой
границы он завышен, а компактность `4πA/P²` систематически занижена: у квадрата
она равна π/4, а не 1. Сравнивать её следует между кронами, а не с кругом.

**Две ошибки легаси-реализации** (`forest_analysis/statistics.py`) здесь не
воспроизводятся, обе закрыты тестами: интенсивность там читалась из размерности Z
(`statistics.py:29`), поэтому все признаки по интенсивности дублировали высоту;
квантили считались как `np.percentile(z, i // 100)` при `i` от 50 до 95
(`statistics.py:61-64`), и целочисленное деление схлопывало все двадцать квантилей
в минимум. Выгрузки `_stats.csv` в бакете, на которых обучался табличный регрессор
диаметра, содержат в этих колонках мусор.

### Согласие с эталоном (`agreement`)

`crown_iou(ours, reference, threshold=0.5) -> Agreement` — сопоставление крон по
максимальному перекрытию и IoU. Возвращает средний и медианный IoU, долю
сопоставленных выше порога и число несопоставленных с обеих сторон.
`rasterize_polygons` и `read_polygons_shp` готовят эталон из shapefile.

Выгрузка СИМА 1.44 — не истина, а результат другого алгоритма с теми же
слабостями, поэтому рост IoU означает «ближе к 1.44», а не «точнее». Независимой
разметки крон нет; рядом с IoU следует смотреть распределение площадей крон.
Сравнивать нужно с объединением `_treesWS.shp` и `_shrubsWS.shp`: легаси делит
кроны порогом 5 м на древостой и кустарник, а наш растр меток содержит все сразу.

### Диаметр ствола (`diameter`)

`estimate_stem_diameter(heights, crown_areas_m2)` — **алгоритм не реализован**,
возвращает NaN. Поле `diam` присутствует в выходных слоях сразу, чтобы схема
shapefile не менялась при появлении расчёта.

### Запись векторов (`vector_io`)

`write_tree_points(xy, out_path, crs_wkt, attributes)` и
`write_crown_polygons(polygons, out_path, crs_wkt, attributes)` — OGR-писатели
с произвольным набором атрибутов. Имена полей обрезаются до 10 символов (предел
DBF), NaN пишется как пустое значение.

### Выходные артефакты

| Артефакт | Формат | Содержание |
|---|---|---|
| ЦМД | GeoTIFF | Растр высот полога (max) |
| Вершины деревьев | Shapefile `*_localMax.shp` | Точки: `hght`, `crown`, `diam` |
| Древостой | Shapefile `*_treesWS.shp` | Полигоны крон высотой ≥ 5 м |
| Кустарник | Shapefile `*_shrubsWS.shp` | Полигоны крон высотой < 5 м |

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
| `filter` | FilterParams | defaults | Параметры фильтров manual/stat/range/outlier |
| `smrf` | SmrfParams | defaults | SMRF: slope=0.2, window=16, threshold=0.45, scalar=1.2 |
| `smoothing` | SmoothingParams | disabled | Гаусс-сглаживание: sigma=2.0, order=0, window=5 |
| `dtm` | DtmParams | defaults | Растеризация ЦМР: output_type=idw |
| `dsm` | DsmParams | disabled | ЦММ (DSM): output_type=max, interpolate=True |
| `derivatives` | DerivativesParams | defaults | Уклон/экспозиция/TPI + интерполяция дырок |
| `vectors` | VectorsParams | defaults | Горизонтали [0.5, 2, 5, 10] м + TIN |
| `heights` | HeightsParams | disabled | Отметки высот: source=las, min_distance_m=10 |
| `deterministic` | bool | False | Детерминизм |
| `seed` | int | 0 | Seed для детерминизма |

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
    SmrfParams, SmoothingParams, DtmParams, DsmParams,
    DerivativesParams, VectorsParams, HeightsParams,
)

params = ReliefParams(
    target_crs="EPSG:32640",
    smoothing=SmoothingParams(enabled=True, sigma=2.0),
    dsm=DsmParams(enabled=True),
    derivatives=DerivativesParams(slopes=True, aspect=True, tpi=True),
    vectors=VectorsParams(horizontals=[0.5, 2.0, 5.0, 10.0], tin=True),
    heights=HeightsParams(enabled=True, source="las", min_distance_m=10.0),
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
| `dtm` | DtmParams | defaults | Растеризация ЦМР |
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
| `elm` | bool | True | Extended Local Minimum (`filters.elm`) — отключаемый |
| `outlier` | bool | True | Statistical outlier removal (`filters.outlier`) — отключаемый |
| `cut_threshold` | float | 3.0 | Порог SMRF в cut-режиме (`cut_smrf=True`) |

#### FilterParams (для manual/stat/range/outlier)

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `spm_min` | float \| None | None | Z_min для manual |
| `spm_max` | float \| None | None | Z_max для manual |
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
| `max_search_distance` | int | 100 | Макс. дистанция поиска для `fill_method="idw"`, px |
| `edge_extrapolation_m` | float | 5.0 | Допустимая экстраполяция за границу данных, м |
| `fill_method` | str | "laplace" | Чем заполняются пустоты: `laplace` или `idw` |
| `fill_passes` | int | 3 | Проходов заполнения пустот |
| `hydro_flatten` | bool | True | Плоская отметка для пустот-водоёмов |

#### DtmParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `output_type` | str | "idw" | Растеризация ЦМР через `writers.gdal`: `idw` / `min` / `max` / `mean` |

Заполнение пустот ЦМР задаётся в `DerivativesParams` — исторически эти поля
живут там, а не в `DtmParams`.

#### DerivativesParams

| Поле | Тип | Default | Описание |
|---|---|---|---|
| `slopes` | bool | False | Построить карту уклонов |
| `slopes_res` | float | 1.0 | Разрешение карты уклонов (м) |
| `aspect` | bool | False | Построить карту экспозиции |
| `aspect_res` | float | 1.0 | Разрешение карты экспозиции (м) |
| `tpi` | bool | False | Построить TPI |
| `tpi_res` | float | 10.0 | Разрешение выходного растра TPI (м) |
| `tpi_radii` | list | [270, 810, 2430] | Радиусы TPI (м) |
| `interpolation` | bool | True | Интерполяция отсутствующих значений ЦМР |
| `inter_amp` | int | 100 | Макс. дистанция интерполяции (м) |
| `edge_extrapolation_m` | float | 5.0 | Допустимая экстраполяция за границу данных, м; `0` — только внутренние дыры |
| `fill_method` | str | "laplace" | Чем заполняются пустоты ЦМР: `laplace` или `idw` |
| `fill_passes` | int | 3 | Проходов заполнения пустот ЦМР |
| `hydro_flatten` | bool | True | Плоская отметка для пустот-водоёмов. На тайлах без водоёмов может ошибочно выровнять крупную пустоту съёмки — см. «Известные отклонения» |

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
| `min_distance_m` | float | 10.0 | Минимальное расстояние между отметками, м (прореживание по расстоянию, не по номеру точки) |

## Координаты: откуда берутся и приводятся ли АФС и ВЛС друг к другу

Короткий ответ: **не приводятся**. Система координат читается из файлов только
для отчёта об исходных материалах; в расчёте она используется как метка, а сами
координаты точек и растров не преобразуются нигде в библиотеке. Ниже — по шагам,
что именно происходит.

### 1. Чтение СК из файла

| Материал | Где читается | Как |
|---|---|---|
| АФС (GeoTIFF) | `assessment.assess_tiff` | `rasterio.open(path).crs` → WKT; при отсутствии СК в файле — пустая строка |
| ВЛС (LAS/LAZ) | `assessment.assess_las` | `laspy.header.parse_crs()` — VLR с GeoTIFF-ключами (LAS ≤ 1.3) или WKT-VLR (LAS 1.4); при ошибке разбора или отсутствии VLR — пустая строка |

`assess_materials` агрегирует каталог так: **СК всего каталога = СК первого
успешно прочитанного тайла**. Расхождение СК между тайлами внутри каталога не
проверяется — упавшим считается только тайл, который не удалось открыть.

Система высот (`vertical_crs` в контракте фронта) из файлов **не извлекается**:
`AfsReport`/`VlsReport` бэкенда такого поля не имеют. Составная СК с вертикальной
компонентой попадёт в `crs` целиком как WKT, отдельным полем — нет.

### 2. Сверка СК внутри пары АФС + ВЛС

Приведения координат нет, поэтому пара с разными СК даёт молча смещённый
результат. Такие тайлы отбраковываются до расчёта:

```python
check = check_pair_crs(vls_path, afs_path)   # assessment.py
check.status   # 'match' | 'mismatch' | 'unknown' | 'single'
check.blocking # True только для 'mismatch'
```

Сравнение ведёт `pyproj`, а не строки: одна и та же система приходит из GeoTIFF
и из LAS разными WKT — другой порядок ключей, другая версия стандарта, EPSG-код
против полного описания. При неразборном WKT — откат на сравнение нормализованных
строк.

| Статус | Когда | Что делает сервис |
|---|---|---|
| `match` | СК совпадают по существу | считает тайл |
| `mismatch` | СК различаются | **тайл пропускается**: `status='skipped'`, причина с обеими СК |
| `unknown` | СК не объявлена хотя бы в одном файле или файл не читается | считает тайл: сверять нечем, а `target_crs` всё равно переопределяет систему при чтении облака |
| `single` | в паре только ВЛС или только АФС | считает тайл |

Сверка видна в таймлайне отдельным шагом `crs_check` — наравне с расчётными,
чтобы пропуск тайла имел объяснение, а успешная сверка подтверждалась. Отключается
через `ReliefService(reject_crs_mismatch=False)`; это оправдано, только когда СК в
файлах объявлена неверно, а фактические координаты совпадают.

### 3. СК в расчёте

`ReliefService.run` не читает СК из входных файлов вообще:

```python
crs = request.params.target_crs   # service.py
```

и передаёт эту строку во все шаги. Дальше она попадает в два места, и оба —
объявление, а не преобразование:

* `readers.las` с `override_srs=crs` (`ground.py`, `dsm.py`, `chm.py`) —
  переопределяет объявленную СК облака. Координаты X/Y/Z остаются как есть;
  если `override_srs` не совпадает с фактической СК точек, PDAL этого не
  заметит — данные просто будут описаны неверно;
* `gdal.SetProjection(crs_wkt)` на выходном растре (`_set_projection`) — пишет
  WKT в метаданные готового GeoTIFF, пикселей не трогает.

**Ни `pyproj.Transformer`, ни `gdal.Warp` со сменой СК, ни `rasterio.warp.reproject`
в конвейере не вызываются.** `gdal.Warp` используется в `curvature.py` и `tpi.py`,
но только для смены разрешения (`xRes`/`yRes`), `dstSRS` там не задаётся.

Практическое следствие: `target_crs` обязан совпадать с фактической СК входного
облака. Если пользователь выберет в интерфейсе другую СК, расчёт пройдёт без
ошибки, а выход получит неверную привязку.

### 4. Где АФС и ВЛС встречаются в одном расчёте

**Рельеф — нигде.** `TileInput.afs_path` используется только в `ReliefService.assess`
(отчёт о материалах). В `_run_tile` он не участвует: ЦМР, ЦММ, производные,
горизонтали, TIN и отметки строятся из одного ВЛС. Снимок в модуле «Рельеф»
нужен только чтобы человек увидел его метаданные.

**Древостой — по экстенту, без СК.** ЦМД строится из ВЛС; снимок нужен для
корректировки вершин (`afs.py`). Сведение двух растров двухступенчатое:

1. окно снимка вырезается по границам ЦМД —
   `rasterio.windows.from_bounds(*chm_bounds, transform=afs.transform)`
   (реализовано в `forest_s3_yuilskiy.ipynb::build_afs_mask`, не в пакете);
2. вырезанное окно прореживается до сетки ЦМД —
   `afs.resample_to_grid(array, shape)`, где `shape` — форма массива ЦМД.

Шаг 1 считает границы ЦМД в системе координат снимка **как есть**, без
преобразования. Шаг 2 работает только с формами массивов: аффинного
преобразования и СК он не видит вовсе — приведение равномерное, из расчёта
«столько-то пикселей снимка на ячейку ЦМД» (при 0.07 м против 0.5 м — около 50).

Отсюда два условия корректности, которые код не проверяет:

* СК снимка и облака должны совпадать — иначе окно вырежется не там, и вершины
  будут сопоставлены с чужими пикселями снимка;
* окно должно покрывать экстент ЦМД целиком; за границами `boundless=True`
  подставляет `fill_value`, и краевые вершины попадут на пустой фон.

### 5. Высоты: ТЛО против абсолютных отметок

Отдельно от плановых координат стоит вертикальная составляющая. Часть исходных
ВЛС хранит **ТЛО** — `Z = HeightAboveGround`, нормализованные относительно земли
высоты, а не абсолютные отметки. Библиотека не различает эти два случая: она
берёт `Z` как есть.

* ЦМР и ЦММ из облака в ТЛО получатся в тех же нормализованных высотах, то есть
  бессмысленными как отметки местности;
* ЦМД, наоборот, от абсолютного уровня не зависит: `CHMBuilder` сам нормализует
  высоты (`filters.hag_delaunay`), поэтому облако в ТЛО и облако в абсолютных
  отметках дают один и тот же растр полога;
* восстановление абсолютных Z по внешней ЦМР реализовано только в харнессе
  бенчмарка (`benchmarks/relief_bench.py::restore_absolute`) — это инструмент
  сверки, а не часть конвейера.

Признак ТЛО косвенно виден в отчёте: `VlsReport.tlo_height_range_m` у
нормализованного облака начинается около нуля (типично −1…22 м), у абсолютного —
равен реальным отметкам участка.

### Что из этого не реализовано

| Ожидание | Факт |
|---|---|
| Приведение ВЛС и АФС к общей СК | Репроекции нет. Расхождение выявляется и тайл отбраковывается |
| Проверка `target_crs` против СК файлов | Нет. Значение принимается на веру |
| Флаг `Scene.reproject` из контракта фронта | В бэкенде не реализован — приводить нечем |
| Извлечение системы высот (`vertical_crs`) | Нет. Только полная строка `crs` |
| Единая СК внутри каталога тайлов | Не проверяется, берётся СК первого тайла |
| Сведение снимка и ЦМД в библиотеке | Логика живёт в ноутбуке, не в `sima-forest-cmd` |

## Ключевые алгоритмические решения

1. **Заполнение пустот — общий механизм** (`sima_dem_core/raster/holes.py::fill_voids`), одинаковый для ЦМР (`ground.py`), сглаживания (`smooth.py`) и ЦММ (`dsm.py`).

   *Что заполняется*: внутренние дырки (окружённые данными, `binary_fill_holes`) плюс пустоты не далее `edge_extrapolation_m` от данных. Область, куда съёмка не заходила, остаётся пустой намеренно — заполнять её значило бы придумывать рельеф.

   *Многопроходность*: маска пересчитывается после каждого прохода. Часть пустот (характерно — водоём, сообщавшийся с внешней пустотой протокой) замыкается в дыру только ПОСЛЕ заполнения соседних, и за один проход остаётся незаполненной. Наружный допуск считается от исходной маски и с проходами не нарастает. Число проходов — `fill_passes` (по умолчанию 3; `1` — прежнее однопроходное поведение).

   *Чем заполняется* — `fill_method`: `"laplace"` (по умолчанию) решает уравнение Лапласа в пустоте с условиями Дирихле по данным; поверхность гладкая по построению и подчиняется принципу максимума. `"idw"` — `GDALFillNodata`, быстрее, но даёт радиальные лучи внутрь крупных пустот и не дотягивается дальше `max_search_distance`. На озере 8 га (`pt000011` Ю-Зимнего) средний \|∇²\| заполненной области: IDW 0.30, Лаплас 0.0026.

   *Гарантия*: валидные ячейки не изменяются ни при каких настройках — финальная перезапись `out[valid] = array[valid]`.

2. **Гидровыравнивание водоёмов** (`sima_dem_core/raster/hydro.py`) — по USGS 3DEP Lidar Base Specification водоём от 0.8 га получает не интерполяцию, а плоскую горизонтальную отметку. Иначе на воду натягиваются высоты берега и древостоя: на том же озере интерполяция давала 37.7…52.5 м вместо уреза 37.7 м. Кандидат — замкнутая (не выходящая за границу съёмки) пустота площадью от `min_water_area_m2`; внутри полосы сканирования такие области практически всегда вода, поскольку суша даёт возвраты хотя бы от растительности. Отметка — нижний квантиль окаймления. Признак косвенный, поэтому при наличии контуров водоёмов (брейклайны, модуль анализа водного слоя) их следует передавать через `water` — тогда стандарт воспроизводится буквально. Включается флагом `hydro_flatten`.

3. **Min-Z fallback из ground-точек** — дырки DTM заполняются минимальными Z из ground-классифицированных точек (не из всех точек).

4. **Склоны по сглаженной DTM** — уклоны и экспозиции строятся по сглаженной DTM, не по сырой.

5. **IDW растеризация** — DTM строится через PDAL `writers.gdal` с `output_type="idw"`.

6. **DSM (ЦММ) через max** — `output_type="max"` берёт максимальную Z по всем точкам в ячейке (после `filters.elm`/`filters.outlier`/`filters.range(Classification[1:5])`/`filters.sample`). Классы 1-5 (unclassified/ground/low-med-high vegetation); строения (класс 6) и прочие классы в ЦММ не попадают — не настраивается через `DSMConfig`, это осознанное отличие от «первой поверхности» ASPRS/ISO-определения DSM, ориентированное на растительность.

7. **TPI трёхмасштабный** — радиусы 270/810/2430 м, `cv2.blur` box filter, нормировка на std. Радиус трактуется как полный размер окна `cv2.blur` (не диаметр/радиус в классическом смысле) — фактический охват вдвое меньше номинального.

8. **Пропуск тайла при ошибке** — упавший тайл → status "failed" + reason, остальные продолжаются.

9. **elm/outlier до финального отбора Classification==2** — и для уже классифицированных LAS (`_build_save_ground_pipeline`), и для сырых (`_build_ground_pipeline`) шумовые точки помечаются классом 7 через `filters.elm`/`filters.outlier` **до** финального `filters.range(Classification[2:2])`, иначе помеченный шум не отсеивается перед растеризацией.

## Известные отклонения от стандартов / открытые вопросы

Зафиксированы аудитом; не баги, но требуют явного продуктового решения перед релизом библиотеки:

- **slope/aspect теряют внешний пиксель растра** — `gdal.DEMProcessing(...)` вызывается без `computeEdges=True`, поэтому крайняя строка/столбец уклона и экспозиции — nodata, даже если исходная ЦМР там валидна (`sima_dem_core/curvature.py`). Важно для бесшовной мозаики тайлов.
- **SMRF использует все типы возвратов** (`SMRFConfig.returns` по умолчанию `first/last/intermediate/only`), а не `last,only`, как рекомендует Pingel et al. 2013 — включение первых/промежуточных возвратов (чаще не-грунтовых в растительности) в SMRF отклоняется от типовой практики.
- **CRS не валидируется** между AOI/LAS/DEM в нескольких местах (`ground.py::_maybe_crop_stage`, `crop.py::Crop.cropCalc`, `height.py`) — риск тихого рассинхрона систем координат при прямом использовании библиотеки вне сервисного слоя.
- **`determinism.py`** выставляет `PYTHONHASHSEED` в `os.environ` уже во время выполнения процесса — эффекта на текущий интерпретатор это не даёт; в проверенном коде не найдено шагов со случайностью, которые seed реально бы фиксировал.
- **`crop.py`** обрезка AOI — точечный `shapely.contains()` в цикле на чистом Python; не рассчитан на объёмы реального LiDAR (10-100M точек), для продуктизации потребует векторизации/пространственного индекса.
- **Гидровыравнивание срабатывает не только на водоёмах** — `hydro_flatten=True` по умолчанию, и крупная пустота съёмки, прошедшая проверки `hydro.flatten_water_voids`, получает плоскую отметку вместо интерполяции. На тайле `P-42-041-239-g` (бенчмарк) это даёт 3.2 % ячеек с ошибкой более метра и поднимает RMSE ЦМР относительно эталона с 0.100 до 0.379 м; на большинстве тайлов эффект отсутствует или в пределах 0.02 м. Параметр вынесен в контракт (`DerivativesParams.hydro_flatten`, `DsmParams.hydro_flatten`) — на участках без водоёмов его следует выключать.
- **`benchmarks/results/results.jsonl` отстаёт от кода** — прогон выполнен до появления гидровыравнивания, поэтому опубликованные метрики точности соответствуют поведению с `hydro_flatten=False`. Перед цитированием цифр бенчмарк нужно перезапустить.
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

237 тестов, 0 неудач: 229 unit + 8 интеграционных. Покрытие с `test_data/` — 80 %.
Полностью покрыты `raster/holes.py`, `raster/hydro.py` и модули `sima-forest-cmd`
кроме `chm.py` (требует PDAL и реального облака — проверяется прогоном ноутбука).
Слабое покрытие: `filters/outlier_filter.py` (43 %), `raster/vectorize.py` (54 %),
`steps.py` (52 %).

`test_treetops.py` фиксирует поведение детекции: округление окна вместо усечения,
схлопывание плато в одну вершину, отсечки по высоте — и отдельно то, что на
отдельно стоящих кронах грубая сетка деревьев **не теряет**, а крона мельче ячейки
исчезает целиком. Слипание крон на грубой сетке синтетикой не воспроизводится,
это эффект сомкнутого полога и измеряется на реальных данных в ноутбуке.

`test_holes.py` отдельно фиксирует гарантии заполнения пустот: неизменность
валидных ячеек при любом числе проходов и любом методе, отсутствие роста области
данных наружу, сходимость проходов, воспроизведение линейной поверхности и
принцип максимума для гармонической интерполяции, порог площади при
гидровыравнивании.

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
| scikit-image | Водораздел при сегментации крон (`segmentation.watershed`) |
| shapely | Геометрия (crop AOI) |
| pyproj | Координатные системы |