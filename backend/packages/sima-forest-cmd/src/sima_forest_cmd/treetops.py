"""Детекция вершин деревьев по ЦМД (модели высот полога).

Классический для ALS-инвентаризации метод локальных максимумов: скользящее окно
берёт максимум высоты, ячейки, равные своему оконному максимуму, объявляются
вершинами. Слипшиеся в плато ячейки одной вершины схлопываются в одну точку по
центру масс, поэтому дерево с плоской макушкой не даёт нескольких стволов.

Размер окна — главный параметр: он задаёт минимальное расстояние между соседними
вершинами и потому напрямую определяет число найденных деревьев. Окно задаётся в
метрах и переводится в радиус ядра в пикселях, то есть физический поперечник окна
равен `2 * window_m + resolution_m`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy import ndimage

# Легаси-константы СИМА 1.44, вынесенные в параметры.
DEFAULT_MIN_HEIGHT_M = 0.5      # ниже — не дерево
DEFAULT_MAX_HEIGHT_M = 60.0     # выше — заведомо шум ЦМД
DEFAULT_SHRUB_HEIGHT_M = 5.0    # граница «кустарник / древостой»


@dataclass
class TreeTops:
    """Результат детекции вершин.

    Attributes:
        rows: строки вершин в сетке растра, субпиксельные (N,).
        cols: столбцы вершин в сетке растра, субпиксельные (N,).
        heights: высота полога в вершине, м (N,).
        markers: целочисленный растр меток; значение k — компонента k-й вершины,
            0 — фон. Используется как маркеры водораздела при сегментации крон.
        window_px: фактический радиус окна поиска в пикселях.
    """

    rows: np.ndarray
    cols: np.ndarray
    heights: np.ndarray
    markers: np.ndarray
    window_px: int

    def __len__(self) -> int:
        return int(self.rows.size)


def disc_kernel(radius_px: int) -> np.ndarray:
    """Дисковое ядро радиуса `radius_px` пикселей, размер (2r+1, 2r+1)."""
    if radius_px < 1:
        raise ValueError(f"Радиус ядра должен быть >= 1 px, получено {radius_px}")
    y, x = np.ogrid[-radius_px:radius_px + 1, -radius_px:radius_px + 1]
    return x ** 2 + y ** 2 <= radius_px ** 2


def window_radius_px(window_m: float, resolution_m: float) -> int:
    """Перевести окно поиска из метров в радиус ядра в пикселях.

    Округление, а не усечение: при усечении окно 0.5 м на растре 0.5 м давало бы
    радиус 0, ядро 1x1, и локальным максимумом становилась бы каждая ячейка.
    """
    if resolution_m <= 0:
        raise ValueError(f"Разрешение должно быть > 0, получено {resolution_m}")
    if window_m < resolution_m:
        raise ValueError(
            f"Окно поиска {window_m} м меньше разрешения растра {resolution_m} м: "
            "окно должно покрывать хотя бы одну ячейку")
    return max(1, int(round(window_m / resolution_m)))


def prepare_chm(
    chm: np.ndarray,
    min_height_m: float = DEFAULT_MIN_HEIGHT_M,
    max_height_m: float = DEFAULT_MAX_HEIGHT_M,
    smooth_radius_px: int = 1,
) -> np.ndarray:
    """Подготовить ЦМД к поиску максимумов: медианное сглаживание и отсечки.

    Сглаживание убирает одиночные выбросы высоты, которые иначе дают ложные
    вершины. Значения вне [min_height_m, max_height_m] и nodata обнуляются:
    ниже нижней отсечки — не дерево, выше верхней — шум.

    Args:
        chm: растр высот полога; nodata — NaN.
        min_height_m: нижняя отсечка высоты, м.
        max_height_m: верхняя отсечка высоты, м.
        smooth_radius_px: радиус медианного ядра, px; 0 — без сглаживания.

    Returns:
        Копия растра с обнулёнными невалидными ячейками.
    """
    work = np.asarray(chm, dtype=float).copy()
    if smooth_radius_px > 0:
        filled = np.where(np.isfinite(work), work, 0.0)
        work = ndimage.median_filter(
            filled, footprint=disc_kernel(smooth_radius_px), mode="nearest")
    work[~np.isfinite(work)] = 0.0
    work[(work < min_height_m) | (work > max_height_m)] = 0.0
    return work


def detect_tree_tops(
    chm: np.ndarray,
    resolution_m: float,
    window_m: float,
    min_height_m: float = DEFAULT_MIN_HEIGHT_M,
    max_height_m: float = DEFAULT_MAX_HEIGHT_M,
    smooth_radius_px: int = 1,
    prepared: bool = False,
    height_from_smoothed: bool = False,
) -> TreeTops:
    """Найти вершины деревьев как локальные максимумы ЦМД.

    Высота дерева по умолчанию снимается с несглаженного растра: медианный фильтр
    срезает макушки и занижает высоту тем сильнее, чем острее крона, — на
    синтетической кроне 23 м сглаживание радиусом 1 px даёт 21.8 м. Сглаживание
    нужно, чтобы не ловить ложные вершины на шуме, но мерить высоту по нему
    значит систематически занижать весь древостой.

    Args:
        chm: растр высот полога, м; nodata — NaN.
        resolution_m: размер ячейки растра, м.
        window_m: окно поиска вершин, м (радиус ядра до перевода в пиксели).
        min_height_m: минимальная высота дерева, м.
        max_height_m: верхняя отсечка высоты, м.
        smooth_radius_px: радиус медианного сглаживания перед поиском, px.
        prepared: True — `chm` уже прошёл `prepare_chm`, повторно не готовить.
        height_from_smoothed: снимать высоту со сглаженного растра (поведение легаси).

    Returns:
        TreeTops; при отсутствии вершин — пустые массивы и нулевые маркеры.
    """
    radius = window_radius_px(window_m, resolution_m)
    work = chm if prepared else prepare_chm(
        chm, min_height_m, max_height_m, smooth_radius_px)
    if height_from_smoothed or prepared:
        source = work
    else:
        source = prepare_chm(chm, min_height_m, max_height_m, smooth_radius_px=0)

    local_max = ndimage.maximum_filter(
        work, footprint=disc_kernel(radius), mode="nearest")
    peaks = (work == local_max) & (work >= min_height_m)

    markers, count = ndimage.label(peaks)
    if count == 0:
        empty = np.empty(0, dtype=float)
        return TreeTops(empty, empty.copy(), empty.copy(),
                        np.zeros(work.shape, dtype=np.int32), radius)

    centres = np.asarray(
        ndimage.center_of_mass(work, markers, range(1, count + 1)), dtype=float)
    rows, cols = centres[:, 0], centres[:, 1]
    heights = source[np.rint(rows).astype(int), np.rint(cols).astype(int)]

    return TreeTops(rows, cols, heights, markers.astype(np.int32), radius)


def to_world(
    tops: TreeTops,
    transform,
    offset: float = 0.5,
) -> np.ndarray:
    """Перевести вершины из сетки растра в координаты СК.

    Args:
        tops: результат детекции.
        transform: аффинное преобразование растра (`rasterio.Affine`).
        offset: сдвиг к центру ячейки; 0.5 — центр, 0.0 — угол.

    Returns:
        Массив (N,3): x, y, высота.
    """
    if len(tops) == 0:
        return np.empty((0, 3), dtype=float)
    xs, ys = transform * (tops.cols + offset, tops.rows + offset)
    return np.column_stack([np.asarray(xs), np.asarray(ys), tops.heights])


def split_by_height(
    heights: np.ndarray,
    shrub_height_m: float = DEFAULT_SHRUB_HEIGHT_M,
) -> tuple[np.ndarray, np.ndarray]:
    """Разделить объекты на древостой и кустарник по высоте.

    Returns:
        (маска древостоя, маска кустарника) — булевы массивы длины N.
    """
    h = np.asarray(heights, dtype=float)
    trees = h >= shrub_height_m
    return trees, ~trees
