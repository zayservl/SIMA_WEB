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
"""

from __future__ import annotations

import numpy as np
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
