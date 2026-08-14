"""Гидровыравнивание водоёмов в растре высот (hydro-flattening).

Лидар не даёт возвратов от водной поверхности, поэтому на месте озера в растре
остаётся пустота. Интерполяция такой пустоты физически неверна: она натягивает
на воду высоты берега и древостоя. Отраслевой стандарт съёмки — USGS 3DEP Lidar
Base Specification (раздел «Hydro-Flattening», Appendix 2) — требует не
интерполировать водоёмы, а задавать им *плоскую горизонтальную* поверхность;
порог по площади в стандарте — 0.8 га (примерно круглый пруд 100 м в поперечнике).

Каноническая реализация опирается на брейклайны — векторные контуры водоёмов,
снятые оператором. В конвейере их нет, поэтому кандидат определяется признаком,
характерным для воздушного лазерного сканирования: **замкнутая** (не выходящая
за границу съёмки) область без единого возврата площадью не меньше `min_area_m2`.
Внутри полосы сканирования такие области — практически всегда вода: любая суша
даёт возвраты хотя бы от растительности. Порог по умолчанию — из стандарта.

Отметка водоёма берётся как нижний квантиль окаймления (`rim_quantile`): по
периметру озера в ЦММ соседствуют и урез воды, и кроны прибрежного леса, и
именно нижняя часть распределения отвечает уровню воды.

Признак остаётся косвенным: крупная замкнутая лакуна не водного происхождения
будет выровнена как водоём. Поэтому, если контуры водоёмов доступны (модуль
анализа водного слоя, брейклайны съёмки), их следует передавать в
`flatten_water_voids` через `water` — тогда стандарт воспроизводится буквально,
а отбор по площади не выполняется.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, label

# Порог площади водоёма из USGS 3DEP Lidar Base Specification: 0.8 га.
MIN_WATER_AREA_M2 = 8000.0


@dataclass
class WaterFlattening:
    """Результат гидровыравнивания."""

    array: np.ndarray           # растр с выровненными водоёмами
    water: np.ndarray           # булева маска выровненных ячеек
    levels: list[float]         # отметка каждого водоёма, м


def flatten_water_voids(
    array: np.ndarray,
    valid: np.ndarray,
    voids: np.ndarray,
    resolution_m: float,
    water: np.ndarray | None = None,
    min_area_m2: float = MIN_WATER_AREA_M2,
    rim_quantile: float = 0.05,
) -> WaterFlattening:
    """Задать пустотам-водоёмам плоскую горизонтальную отметку.

    Args:
        array: растр высот; в пустотах значения произвольны (nodata или уже
            интерполированные — они будут заменены).
        valid: маска ячеек с измерениями; только они дают отметку уреза.
        voids: маска пустот-кандидатов (связные области рассматриваются по
            отдельности).
        resolution_m: размер ячейки, м — переводит порог площади в пиксели.
        water: готовая маска водоёмов (брейклайны, слой анализа воды). Если
            задана, отбор по площади не выполняется.
        min_area_m2: минимальная площадь водоёма; по умолчанию порог 3DEP.
        rim_quantile: квантиль окаймления, дающий отметку воды.

    Returns:
        WaterFlattening: растр, маска выровненных ячеек и отметки водоёмов.
        Если ни один кандидат не прошёл отбор, растр возвращается без изменений.

    Валидные ячейки не изменяются: выравнивание пишется только по маске пустот.
    """
    out = array.copy()
    flattened = np.zeros(array.shape, dtype=bool)
    levels: list[float] = []

    candidates = np.asarray(voids, dtype=bool) if water is None else (
        np.asarray(water, dtype=bool) & np.asarray(voids, dtype=bool))
    if not candidates.any():
        return WaterFlattening(out, flattened, levels)

    min_area_px = _area_px(min_area_m2, resolution_m)
    labelled, count = label(candidates)
    for i in range(1, count + 1):
        region = labelled == i
        if water is None and region.sum() < min_area_px:
            continue
        rim = binary_dilation(region) & valid
        if not rim.any():
            continue
        level = float(np.quantile(array[rim], rim_quantile))
        out[region] = level
        flattened |= region
        levels.append(level)

    return WaterFlattening(out, flattened, levels)


def _area_px(area_m2: float, resolution_m: float) -> float:
    """Перевести площадь в квадратных метрах в число ячеек растра."""
    if resolution_m <= 0:
        return float("inf")
    return float(area_m2) / (float(resolution_m) ** 2)
