"""Диаметр ствола — интерфейс зафиксирован, алгоритм не реализован.

Поле диаметра присутствует в выходных слоях с самого начала, чтобы схема
shapefile не менялась при появлении расчёта: потребители атрибутов пишутся один
раз. До реализации функция возвращает NaN — это отличает «не считали» от
посчитанного нуля.
"""

from __future__ import annotations

import numpy as np


def estimate_stem_diameter(
    heights: np.ndarray,
    crown_areas_m2: np.ndarray | None = None,
) -> np.ndarray:
    """Оценить диаметр ствола по высоте и площади кроны.

    НЕ РЕАЛИЗОВАНО: возвращает массив NaN нужной длины.

    Args:
        heights: высоты деревьев, м (N,).
        crown_areas_m2: площади крон, м² (N,) — будущий предиктор.

    Returns:
        Массив (N,) диаметров, м; сейчас — NaN.
    """
    return np.full(np.asarray(heights).shape, np.nan, dtype=float)
