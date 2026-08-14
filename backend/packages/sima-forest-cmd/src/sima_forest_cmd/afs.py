"""Корректировка вершин деревьев по аэрофотоснимку.

ЦМД не отличает дерево от столба, мачты или бровки отвала: всё это возвышается
над землёй и даёт локальный максимум высоты. Снимок различает их по цвету, и это
единственный доступный здесь признак — съёмка ведётся в видимом диапазоне, канала
ближнего ИК нет, поэтому NDVI неприменим. Используются индексы по RGB:

* ExG (excess green) = 2g − r − b по нормированным каналам — устойчив к яркости,
  стандартный выбор для RGB-съёмки растительности;
* VARI = (g − r) / (g + r − b) — сильнее реагирует на слабую зелень, но шумит на
  тенях и переэкспонированных участках.

Две операции, обе выключаются независимо:

* отсев — вершина вне маски растительности не дерево;
* уточнение — вершина сдвигается к центру связной области кроны на снимке, если
  та нашлась в пределах заданного радиуса.

Модуль работает только при переданном снимке; без него вызывающий код идёт тем же
путём, просто не вызывая эти функции.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

DEFAULT_EXG_THRESHOLD = 0.05
DEFAULT_REFINE_RADIUS_M = 1.5


@dataclass
class VegetationMask:
    """Маска растительности, приведённая к сетке ЦМД."""

    mask: np.ndarray
    index: np.ndarray          # значения вегетационного индекса
    method: str
    threshold: float
    coverage_pct: float


@dataclass
class TopsCorrection:
    """Статистика корректировки — без неё этап невозможно отладить."""

    keep: np.ndarray                                  # булева маска оставленных вершин
    rows: np.ndarray                                  # строки после уточнения
    cols: np.ndarray                                  # столбцы после уточнения
    dropped: int = 0
    moved: int = 0
    shift_px: np.ndarray = field(default_factory=lambda: np.empty(0))


def vegetation_index(rgb: np.ndarray, method: str = "exg") -> np.ndarray:
    """Вегетационный индекс по RGB-снимку.

    Args:
        rgb: массив (3,H,W) или (H,W,3); допускается uint8 или float.
        method: "exg" или "vari".

    Returns:
        Массив (H,W) значений индекса; вне диапазона данных — NaN.
    """
    arr = np.asarray(rgb, dtype=float)
    if arr.ndim != 3:
        raise ValueError(f"Ожидался трёхканальный растр, получено {arr.shape}")
    if arr.shape[0] == 3:
        arr = np.moveaxis(arr, 0, -1)
    if arr.shape[-1] < 3:
        raise ValueError(f"Нужно минимум 3 канала, получено {arr.shape[-1]}")

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    total = r + g + b
    with np.errstate(divide="ignore", invalid="ignore"):
        if method == "exg":
            rn, gn, bn = r / total, g / total, b / total
            index = 2.0 * gn - rn - bn
        elif method == "vari":
            index = (g - r) / (g + r - b)
        else:
            raise ValueError(f"Неизвестный индекс: {method!r}; ожидается 'exg' или 'vari'")
    index[~np.isfinite(index)] = np.nan
    return index


def vegetation_mask(
    rgb: np.ndarray,
    method: str = "exg",
    threshold: float = DEFAULT_EXG_THRESHOLD,
    min_area_px: int = 0,
) -> VegetationMask:
    """Построить маску растительности по снимку.

    Args:
        rgb: снимок (3,H,W) или (H,W,3).
        method: индекс — "exg" или "vari".
        threshold: порог индекса; выше — растительность.
        min_area_px: выбрасывать связные пятна меньше этой площади, px.

    Returns:
        VegetationMask в сетке снимка.
    """
    index = vegetation_index(rgb, method)
    mask = np.isfinite(index) & (index >= threshold)

    if min_area_px > 0 and mask.any():
        labels, count = ndimage.label(mask)
        if count:
            sizes = np.bincount(labels.ravel())
            small = np.zeros(sizes.size, dtype=bool)
            small[1:] = sizes[1:] < min_area_px
            mask &= ~small[labels]

    return VegetationMask(
        mask=mask, index=index, method=method, threshold=threshold,
        coverage_pct=100.0 * float(mask.mean()) if mask.size else 0.0,
    )


def resample_mask_to_grid(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Привести маску снимка к сетке ЦМД ближайшим соседом.

    Снимок обычно на порядок подробнее ЦМД (0.07 м против 0.5 м), поэтому
    приведение всегда идёт с прореживанием.

    Args:
        mask: булева маска в сетке снимка.
        shape: (rows, cols) целевой сетки.

    Returns:
        Булева маска формы `shape`.
    """
    mask = np.asarray(mask, dtype=bool)
    if mask.shape == tuple(shape):
        return mask
    rows = np.clip((np.arange(shape[0]) + 0.5) * mask.shape[0] / shape[0],
                   0, mask.shape[0] - 1).astype(int)
    cols = np.clip((np.arange(shape[1]) + 0.5) * mask.shape[1] / shape[1],
                   0, mask.shape[1] - 1).astype(int)
    return mask[np.ix_(rows, cols)]


def correct_tops(
    rows: np.ndarray,
    cols: np.ndarray,
    veg_mask: np.ndarray,
    resolution_m: float,
    drop_non_vegetation: bool = True,
    refine_position: bool = True,
    refine_radius_m: float = DEFAULT_REFINE_RADIUS_M,
) -> TopsCorrection:
    """Отсеять и уточнить вершины по маске растительности.

    Отсев: вершина, попавшая вне маски, отбрасывается как не дерево.
    Уточнение: вершина сдвигается в центр масс связной области растительности,
    которой она принадлежит, но не дальше `refine_radius_m` — дальний сдвиг
    означает, что вершина принадлежит слитному пологу, а не отдельной кроне,
    и исходное положение по ЦМД надёжнее.

    Args:
        rows: строки вершин в сетке ЦМД (N,).
        cols: столбцы вершин в сетке ЦМД (N,).
        veg_mask: маска растительности в сетке ЦМД.
        resolution_m: размер ячейки ЦМД, м.
        drop_non_vegetation: включить отсев.
        refine_position: включить уточнение положения.
        refine_radius_m: максимальный сдвиг вершины, м.

    Returns:
        TopsCorrection с маской оставленных вершин, новыми координатами и статистикой.
    """
    rows = np.asarray(rows, dtype=float)
    cols = np.asarray(cols, dtype=float)
    n = rows.size
    keep = np.ones(n, dtype=bool)
    if n == 0:
        return TopsCorrection(keep, rows, cols)

    veg_mask = np.asarray(veg_mask, dtype=bool)
    ri = np.clip(np.rint(rows).astype(int), 0, veg_mask.shape[0] - 1)
    ci = np.clip(np.rint(cols).astype(int), 0, veg_mask.shape[1] - 1)
    on_vegetation = veg_mask[ri, ci]

    if drop_non_vegetation:
        keep = on_vegetation

    new_rows, new_cols = rows.copy(), cols.copy()
    shift = np.zeros(n, dtype=float)

    if refine_position and veg_mask.any():
        labels, count = ndimage.label(veg_mask)
        if count:
            centres = np.asarray(
                ndimage.center_of_mass(veg_mask, labels, range(1, count + 1)),
                dtype=float)
            at = labels[ri, ci]
            has_blob = at > 0
            cand_r = np.where(has_blob, centres[np.maximum(at - 1, 0), 0], rows)
            cand_c = np.where(has_blob, centres[np.maximum(at - 1, 0), 1], cols)
            dist_px = np.hypot(cand_r - rows, cand_c - cols)
            within = has_blob & (dist_px * resolution_m <= refine_radius_m)
            new_rows = np.where(within, cand_r, rows)
            new_cols = np.where(within, cand_c, cols)
            shift = np.where(within, dist_px, 0.0)

    return TopsCorrection(
        keep=keep,
        rows=new_rows,
        cols=new_cols,
        dropped=int((~keep).sum()),
        moved=int((shift > 0).sum()),
        shift_px=shift,
    )
