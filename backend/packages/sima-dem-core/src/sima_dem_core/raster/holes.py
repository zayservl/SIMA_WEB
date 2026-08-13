"""Выбор ячеек растра, подлежащих заполнению интерполяцией.

Общий хелпер для ЦМР (`sima_dem_ground.ground`), ЦММ (`sima_dem_dsm.dsm`) и
сглаживания (`sima_dem_core.raster.smooth`) — раньше правило было продублировано
в трёх местах.

Историческое поведение: «дырой» считался только nodata-регион, полностью
окружённый валидными данными (`binary_fill_holes`). Любая пустота, касающаяся
рамки растра, не заполнялась — независимо от того, насколько близко реальные
данные. На разреженных облаках это выбрасывало десятки процентов площади:
на тайле P-42-042-249-a бенчмарка — 76 % растра при 23 % валидных ячеек.

Топологический критерий заменён на дистанционный: помимо внутренних дыр
заполняются ячейки не далее `max_extrapolation_px` от валидных данных. Это
контролируемая экстраполяция на заданное расстояние вместо «всё или ничего».
При `max_extrapolation_px=0` поведение совпадает с историческим.

`fill_voids` выполняет само заполнение: маска дыр пересчитывается после каждого
прохода, потому что часть пустот становится внутренними дырами только ПОСЛЕ
заполнения соседних (см. док-строку функции).
"""

from __future__ import annotations

import numpy as np
from rasterio.fill import fillnodata
from scipy.ndimage import binary_fill_holes, distance_transform_edt


def fillable_mask(valid: np.ndarray, max_extrapolation_px: float = 0.0) -> np.ndarray:
    """Маска ячеек nodata, которые следует заполнить.

    Args:
        valid: булева маска валидных (не-nodata) ячеек растра.
        max_extrapolation_px: максимальное расстояние в пикселях, на которое
            допускается экстраполяция за границу валидной области. 0 — только
            внутренние дыры (историческое поведение).

    Returns:
        Булева маска той же формы: True — ячейку нужно заполнить.
    """
    valid = np.asarray(valid, dtype=bool)
    empty = ~valid
    holes = binary_fill_holes(valid) & empty
    if max_extrapolation_px and max_extrapolation_px > 0 and empty.any() and valid.any():
        near = distance_transform_edt(empty) <= max_extrapolation_px
        holes = holes | (empty & near)
    return holes


def px_from_metres(distance_m: float, resolution_m: float) -> float:
    """Перевести расстояние в метрах в пиксели растра. При res<=0 — 0.0."""
    if not distance_m or distance_m <= 0 or not resolution_m or resolution_m <= 0:
        return 0.0
    return float(distance_m) / float(resolution_m)


def fill_voids(
    array: np.ndarray,
    valid: np.ndarray,
    max_search_distance: int = 100,
    smoothing_iterations: int = 0,
    max_extrapolation_px: float = 0.0,
    max_passes: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Заполнить пустоты растра интерполяцией, не изменяя валидные ячейки.

    Один проход `fillnodata` оставляет незаполненными пустоты, которые
    становятся внутренними дырами только ПОСЛЕ заполнения соседних: маска
    считается до заполнения, поэтому водоём, сообщавшийся с внешней пустотой
    узкой перемычкой, замыкается заполнением этой перемычки и остаётся дырой.
    Каждый следующий проход пересчитывает маску по обновлённой валидной области
    и берёт то, что замкнулось. Цикл прекращается, как только очередной проход
    не добавил ни одной ячейки.

    Наружу область данных при этом не разрастается: допуск
    `max_extrapolation_px` считается один раз от ИСХОДНОЙ валидной маски, а
    последующие проходы добавляют только внутренние дыры. Иначе каждый проход
    отодвигал бы границу ещё на `max_extrapolation_px`.

    Гарантия: `out[valid] == array[valid]` поэлементно при любом числе проходов —
    исходные измерения не переинтерполируются и не сглаживаются.

    Args:
        array: значения растра (в пустотах — nodata).
        valid: булева маска валидных ячеек.
        max_search_distance: радиус поиска `fillnodata`, px.
        smoothing_iterations: сглаживание заполненных значений внутри `fillnodata`.
        max_extrapolation_px: допустимая экстраполяция за границу данных, px.
        max_passes: максимум проходов; 1 — историческое однопроходное поведение.

    Returns:
        (out, filled) — растр с заполненными пустотами и маска заполненных ячеек.
    """
    array = np.asarray(array)
    valid = np.asarray(valid, dtype=bool)
    work = array.copy()
    filled = np.zeros(array.shape, dtype=bool)

    # Наружный допуск фиксируем по исходным данным — он не должен нарастать с проходами.
    edge_allowance = fillable_mask(valid, max_extrapolation_px)

    for _ in range(max(1, int(max_passes))):
        current = valid | filled
        holes = (fillable_mask(current) | edge_allowance) & ~current
        if not holes.any():
            break
        candidate = fillnodata(
            work.copy(),
            mask=np.where(current, 255, 0).astype("uint8"),
            max_search_distance=max_search_distance,
            smoothing_iterations=smoothing_iterations,
        )
        new = holes & (candidate != work)   # дотянулось не всё: за max_search_distance значение не меняется
        if not new.any():
            break
        work[new] = candidate[new]
        filled |= new

    work[valid] = array[valid]              # жёсткая гарантия неизменности исходных ячеек
    return work, filled
