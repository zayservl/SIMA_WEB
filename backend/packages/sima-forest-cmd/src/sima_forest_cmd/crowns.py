"""Сегментация крон по ЦМД маркер-контролируемым водоразделом.

Крона отделяется от соседних заливкой от вершины вниз по склону полога: рельеф
высот инвертируется, вершины деревьев служат маркерами-источниками, граница между
зонами заливки проходит по «седловине» между кронами. Заливка ограничена маской
полога, поэтому в межкроновые просветы и на землю она не уходит.

Каждой вершине соответствует ровно одна зона: маркеры берутся из детекции вершин,
новых источников водораздел не создаёт.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from rasterio import features
from skimage.segmentation import watershed

from .treetops import DEFAULT_MIN_HEIGHT_M, TreeTops


@dataclass
class Crowns:
    """Результат сегментации крон.

    Attributes:
        labels: растр меток; значение k — крона k-й вершины, 0 — фон.
        polygons: список геометрий в формате GeoJSON-словарей, по одной на крону.
        tree_index: индекс вершины для каждого полигона (совпадает с меткой − 1).
        areas_m2: площадь кроны, м².
    """

    labels: np.ndarray
    polygons: list
    tree_index: np.ndarray
    areas_m2: np.ndarray

    def __len__(self) -> int:
        return len(self.polygons)


def delineate_crowns(
    chm: np.ndarray,
    tops: TreeTops,
    min_height_m: float = DEFAULT_MIN_HEIGHT_M,
    surface: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Построить растр меток крон водоразделом от маркеров-вершин.

    Args:
        chm: растр высот полога, м; nodata — NaN.
        tops: вершины с маркерами (результат `detect_tree_tops`).
        min_height_m: нижняя граница полога — ниже неё заливка запрещена.
        surface: готовая поверхность стоимости (`cost.build_cost_surface`).
            None — заливка по `−CHM`, то есть только по высоте.

    Returns:
        Целочисленный растр меток той же формы, что `chm`; 0 — вне крон.

    Маска полога и маркеры от поверхности не зависят, поэтому число крон всегда
    равно числу вершин — поверхность меняет только положение границ между ними.
    """
    work = np.asarray(chm, dtype=float)
    work = np.where(np.isfinite(work), work, 0.0)
    canopy = work >= min_height_m
    if len(tops) == 0 or not canopy.any():
        return np.zeros(work.shape, dtype=np.int32)
    if surface is None:
        # Водораздел заливает от минимумов, поэтому подаём инвертированный полог:
        # вершина дерева становится дном воронки, седловина между кронами — гребнем.
        relief = -work
    else:
        relief = np.asarray(surface, dtype=float)
        if relief.shape != work.shape:
            raise ValueError(
                f"Поверхность стоимости {relief.shape} не совпадает с ЦМД {work.shape}")
    labels = watershed(relief, markers=tops.markers, mask=canopy)
    return labels.astype(np.int32)


def _ring_area(ring) -> float:
    """Площадь кольца по формуле шнурков, м²."""
    pts = np.asarray(ring, dtype=float)
    if pts.shape[0] < 4:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1])))


def _polygon_area(geom: dict) -> float:
    """Площадь GeoJSON-полигона за вычетом отверстий, м²."""
    rings = geom.get("coordinates") or []
    if not rings:
        return 0.0
    return _ring_area(rings[0]) - sum(_ring_area(r) for r in rings[1:])


def crowns_to_polygons(
    labels: np.ndarray,
    transform,
    resolution_m: float = 1.0,
) -> Crowns:
    """Векторизовать растр меток крон в полигоны.

    Отверстия внутри кроны не заполняются: пропуски полога — реальные просветы,
    и затягивать их означало бы завышать площадь кроны. Крона из нескольких
    несвязных кусков даёт несколько полигонов с одним и тем же `tree_index`.

    Args:
        labels: растр меток крон (`delineate_crowns`).
        transform: аффинное преобразование растра (`rasterio.Affine`).
        resolution_m: размер ячейки, м — оставлен для совместимости сигнатуры;
            площадь считается по геометрии полигона, а не по числу ячеек.

    Returns:
        Crowns с полигонами, индексами деревьев и площадями.
    """
    labels = np.asarray(labels, dtype=np.int32)
    polygons: list = []
    indices: list = []
    areas: list = []

    for geom, value in features.shapes(labels, mask=labels > 0, transform=transform):
        polygons.append(geom)
        indices.append(int(value) - 1)
        areas.append(_polygon_area(geom))

    return Crowns(
        labels=labels,
        polygons=polygons,
        tree_index=np.asarray(indices, dtype=int),
        areas_m2=np.asarray(areas, dtype=float),
    )


def crown_areas_by_tree(labels: np.ndarray, n_trees: int, resolution_m: float) -> np.ndarray:
    """Площадь кроны для каждой вершины, м². Для вершин без кроны — 0.

    Args:
        labels: растр меток крон.
        n_trees: число вершин.
        resolution_m: размер ячейки, м.
    """
    if n_trees == 0:
        return np.empty(0, dtype=float)
    counts = np.bincount(np.asarray(labels, dtype=np.int64).ravel(),
                         minlength=n_trees + 1)[1:n_trees + 1]
    return counts.astype(float) * float(resolution_m) ** 2
