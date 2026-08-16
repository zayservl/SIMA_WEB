"""Согласие сегментации крон с эталонным набором полигонов.

Считает IoU между нашими кронами и эталонными: для каждой эталонной кроны
берётся наша с наибольшим перекрытием. Метрики — средний IoU по сопоставленным,
доля сопоставленных при IoU выше порога и доли несопоставленных с обеих сторон:
пропущенные эталонные кроны и наши лишние.

Важно, чем это является и чем не является. Выгрузка СИМА 1.44 — не истина, а
результат другого алгоритма с теми же слабостями. Рост IoU означает «ближе к
1.44», а не «точнее». Независимой разметки крон нет, поэтому рядом с IoU всегда
следует смотреть распределение площадей: слипание крон даёт тяжёлый правый хвост
и видно без эталона (`crowns.crown_areas_by_tree`, `features.crown_geometry`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from rasterio import features


@dataclass
class Agreement:
    """Результат сравнения двух наборов крон."""

    mean_iou: float                 # средний IoU по сопоставленным парам
    median_iou: float
    matched_share: float            # доля эталонных крон с IoU выше порога
    n_reference: int
    n_ours: int
    n_matched: int
    unmatched_reference: int        # эталонные кроны без пары
    unmatched_ours: int             # наши кроны, не ставшие ничьей парой
    iou: np.ndarray                 # IoU для каждой эталонной кроны (0 — пары нет)
    threshold: float = 0.5


def rasterize_polygons(
    geometries: Sequence,
    shape: tuple,
    transform,
) -> np.ndarray:
    """Растеризовать полигоны в растр меток 1..N на заданной сетке.

    Args:
        geometries: геометрии в формате GeoJSON-словарей.
        shape: (rows, cols) целевой сетки.
        transform: аффинное преобразование сетки.

    Returns:
        Растр int32; 0 — фон.
    """
    if not len(geometries):
        return np.zeros(shape, dtype=np.int32)
    shapes = ((geom, i) for i, geom in enumerate(geometries, start=1))
    return features.rasterize(shapes, out_shape=shape, transform=transform,
                              fill=0, dtype="int32")


def read_polygons_shp(path: str) -> list:
    """Прочитать полигоны из shapefile в список GeoJSON-словарей."""
    from osgeo import ogr

    ds = ogr.Open(path)
    if ds is None:
        return []
    layer = ds.GetLayer()
    import json
    geometries = []
    for feature in layer:
        geom = feature.GetGeometryRef()
        if geom is not None:
            geometries.append(json.loads(geom.ExportToJson()))
    ds = None
    return geometries


def crown_iou(
    ours: np.ndarray,
    reference: np.ndarray,
    threshold: float = 0.5,
) -> Agreement:
    """Сопоставить кроны по максимальному перекрытию и посчитать IoU.

    Каждой эталонной кроне подбирается наша с наибольшим пересечением; одна наша
    крона может оказаться лучшей парой для нескольких эталонных — это признак
    слипания, и он виден по разнице `n_matched` и числа уникальных пар.

    Args:
        ours: растр меток наших крон.
        reference: растр меток эталонных крон той же формы.
        threshold: порог IoU, при котором пара считается сопоставленной.

    Returns:
        Agreement с метриками согласия.
    """
    ours = np.asarray(ours, dtype=np.int64)
    reference = np.asarray(reference, dtype=np.int64)
    if ours.shape != reference.shape:
        raise ValueError(f"Формы растров {ours.shape} и {reference.shape} не совпадают")

    n_ours = int(ours.max())
    n_ref = int(reference.max())
    if n_ref == 0 or n_ours == 0:
        return Agreement(float("nan"), float("nan"), 0.0, n_ref, n_ours, 0,
                         n_ref, n_ours, np.zeros(max(n_ref, 0)), threshold)

    area_ours = np.bincount(ours.ravel(), minlength=n_ours + 1)
    area_ref = np.bincount(reference.ravel(), minlength=n_ref + 1)

    both = (ours > 0) & (reference > 0)
    best_inter = np.zeros(n_ref + 1, dtype=np.int64)
    best_ours = np.zeros(n_ref + 1, dtype=np.int64)
    if both.any():
        # Пары кодируются одним числом, чтобы посчитать пересечения одним проходом
        # np.unique вместо перебора десятков тысяч пар «наша крона — эталонная».
        pair = ours[both] * (n_ref + 1) + reference[both]
        unique, counts = np.unique(pair, return_counts=True)
        pair_ours, pair_ref = np.divmod(unique, n_ref + 1)
        # Сортировка по (эталон, перекрытие): последняя запись каждой эталонной
        # кроны — её лучшая пара.
        order = np.lexsort((counts, pair_ref))
        ref_sorted = pair_ref[order]
        last = np.searchsorted(ref_sorted, np.arange(1, n_ref + 1), side="right") - 1
        exists = (last >= 0) & (ref_sorted[np.maximum(last, 0)] == np.arange(1, n_ref + 1))
        idx = order[np.maximum(last, 0)]
        best_inter[1:][exists] = counts[idx][exists]
        best_ours[1:][exists] = pair_ours[idx][exists]

    inter = best_inter[1:]
    union = area_ref[1:n_ref + 1] + area_ours[best_ours[1:]] - inter
    iou = np.where((inter > 0) & (union > 0), inter / np.maximum(union, 1), 0.0)

    matched = iou >= threshold
    paired = set(int(v) for v in best_ours[1:] if v > 0)
    return Agreement(
        mean_iou=float(iou[iou > 0].mean()) if (iou > 0).any() else 0.0,
        median_iou=float(np.median(iou[iou > 0])) if (iou > 0).any() else 0.0,
        matched_share=float(matched.mean()),
        n_reference=n_ref,
        n_ours=n_ours,
        n_matched=int(matched.sum()),
        unmatched_reference=int((iou == 0).sum()),
        unmatched_ours=n_ours - len(paired),
        iou=iou,
        threshold=threshold,
    )
