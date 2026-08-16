"""Признаки каждой кроны: геометрия, структура высот, сигнал ВЛС.

Таблица признаков — вход для будущей оценки диаметра ствола и материал для
контроля качества сегментации: слипшиеся кроны видно по тяжёлому правому хвосту
распределения площадей и по низкой компактности.

Точки облака привязываются к кронам через растр меток: координаты точки
переводятся обратным геотрансформом в (row, col) и берётся `labels[row, col]`.
Это один проход по массиву вместо пространственного соединения полигонов и не
требует geopandas.

Две ошибки легаси-реализации (`forest_analysis/statistics.py`) здесь не
воспроизводятся, обе закрыты тестами:

* интенсивность там читалась из размерности Z, поэтому все признаки по
  интенсивности дублировали высоту;
* квантили считались как `np.percentile(z, i // 100)` при `i` от 50 до 95 —
  целочисленное деление давало 0, и все квантили схлопывались в минимум.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

DEFAULT_PERCENTILES = (50, 55, 60, 65, 70, 75, 80, 85, 90, 95)
DEFAULT_VCI_STEP_M = 1.0
ROBUST_HEIGHT_PERCENTILE = 99.0

# Доля самых высоких ячеек, отбрасываемых при расчёте устойчивой высоты.
# Перцентиль здесь не годится: медианная крона на реальных данных — 15–20 ячеек
# при разрешении 0.5 м, и одиночный выброс на 36 ячейках попадает выше 97-го
# перцентиля, то есть p99 почти совпадает с максимумом. Отбрасывание доли, но
# не менее одной ячейки, работает одинаково на кронах любого размера.
DEFAULT_HEIGHT_TRIM = 0.05


@dataclass
class CrownFeatures:
    """Признаки крон, по одной строке на дерево.

    Attributes:
        tree_id: метка кроны в растре (1..N).
        columns: имя признака -> массив длины N.
    """

    tree_id: np.ndarray
    columns: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.tree_id.size)

    def to_dict(self) -> dict:
        return {"tree_id": self.tree_id, **self.columns}


def _counts(labels: np.ndarray, n_trees: int) -> np.ndarray:
    return np.bincount(labels.ravel(), minlength=n_trees + 1)[1:n_trees + 1]


def _sum_by_label(labels_flat: np.ndarray, values: np.ndarray, n_trees: int) -> np.ndarray:
    return np.bincount(labels_flat, weights=values, minlength=n_trees + 1)[1:n_trees + 1]


def crown_geometry(
    labels: np.ndarray,
    n_trees: int,
    resolution_m: float,
    apex_rows: Optional[np.ndarray] = None,
    apex_cols: Optional[np.ndarray] = None,
) -> dict:
    """Геометрия каждой кроны по растру меток.

    Периметр считается по числу рёбер между ячейкой кроны и её соседом иной
    метки; для ступенчатой границы это завышенная оценка по сравнению с гладким
    контуром, поэтому компактность здесь занижена систематически и сравнивать её
    следует между кронами, а не с теоретической единицей круга.

    Args:
        labels: растр меток крон.
        n_trees: число деревьев.
        resolution_m: размер ячейки, м.
        apex_rows: строки вершин — для смещения вершины от центроида.
        apex_cols: столбцы вершин.

    Returns:
        Словарь имя признака -> массив длины `n_trees`.
    """
    labels = np.asarray(labels, dtype=np.int64)
    cell = float(resolution_m) ** 2
    counts = _counts(labels, n_trees)
    area = counts.astype(float) * cell

    # Периметр: рёбра между разными метками по обеим осям, включая рамку растра.
    padded = np.pad(labels, 1, mode="constant", constant_values=0)
    edges = np.zeros(n_trees + 1, dtype=np.int64)
    for shift_axis in (0, 1):
        a = padded
        b = np.roll(padded, 1, axis=shift_axis)
        differ = a != b
        for side in (a, b):
            values = side[differ]
            edges += np.bincount(values[values > 0], minlength=n_trees + 1)
    perimeter = edges[1:n_trees + 1].astype(float) * float(resolution_m)

    rows, cols = np.nonzero(labels)
    flat = labels[rows, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        centroid_r = _sum_by_label(flat, rows.astype(float), n_trees) / np.maximum(counts, 1)
        centroid_c = _sum_by_label(flat, cols.astype(float), n_trees) / np.maximum(counts, 1)
        equivalent = 2.0 * np.sqrt(area / np.pi)
        compactness = np.where(perimeter > 0,
                               4.0 * np.pi * area / np.square(perimeter), np.nan)

    out = {
        "area_m2": area,
        "perimeter_m": perimeter,
        "equivalent_diameter_m": equivalent,
        "compactness": compactness,
        "n_cells": counts.astype(float),
    }
    if apex_rows is not None and apex_cols is not None:
        offset = np.hypot(np.asarray(apex_rows, dtype=float)[:n_trees] - centroid_r,
                          np.asarray(apex_cols, dtype=float)[:n_trees] - centroid_c)
        out["apex_offset_m"] = offset * float(resolution_m)
    return out


def crown_height_structure(
    labels: np.ndarray,
    chm: np.ndarray,
    n_trees: int,
    percentiles: tuple = DEFAULT_PERCENTILES,
    height_trim: float = DEFAULT_HEIGHT_TRIM,
) -> dict:
    """Статистики высоты полога внутри каждой кроны.

    Три оценки высоты дерева, каждая со своим смыслом:

    * `chm_max_m` — максимум, воспроизводит легаси, но принимает любой выброс ЦМД
      за макушку;
    * `chm_p99_m` — 99-й перцентиль; на крупных кронах устойчив, на мелких почти
      совпадает с максимумом (на 36 ячейках p99 отстоит от максимума на 3 %);
    * `height_robust_m` — максимум после отбрасывания доли `height_trim` самых
      высоких ячеек, но не менее одной. Работает на кронах любого размера, что и
      требуется: медианная крона на реальных данных — 15–20 ячеек.

    Args:
        labels: растр меток крон.
        chm: растр высот полога.
        n_trees: число деревьев.
        percentiles: какие квантили считать.
        height_trim: доля отбрасываемых верхних ячеек для устойчивой высоты.
    """
    labels = np.asarray(labels, dtype=np.int64)
    chm = np.asarray(chm, dtype=float)
    rows, cols = np.nonzero(labels)
    flat = labels[rows, cols]
    values = np.where(np.isfinite(chm[rows, cols]), chm[rows, cols], 0.0)

    counts = np.maximum(_counts(labels, n_trees), 1).astype(float)
    total = _sum_by_label(flat, values, n_trees)
    mean = total / counts
    total_sq = _sum_by_label(flat, values * values, n_trees)
    std = np.sqrt(np.maximum(total_sq / counts - mean * mean, 0.0))

    out = {"chm_mean_m": mean, "chm_std_m": std}
    order = np.argsort(flat, kind="stable")
    grouped_labels, grouped_values = flat[order], values[order]
    starts = np.searchsorted(grouped_labels, np.arange(1, n_trees + 1), side="left")
    ends = np.searchsorted(grouped_labels, np.arange(1, n_trees + 1), side="right")

    wanted = list(percentiles) + [ROBUST_HEIGHT_PERCENTILE, 100.0]
    quantile_values = {p: np.full(n_trees, np.nan) for p in wanted}
    robust = np.full(n_trees, np.nan)
    for i, (lo, hi) in enumerate(zip(starts, ends)):
        if hi <= lo:
            continue
        chunk = grouped_values[lo:hi]
        for p, value in zip(wanted, np.percentile(chunk, wanted)):
            quantile_values[p][i] = value
        drop = min(max(1, int(round(chunk.size * height_trim))), chunk.size - 1)
        robust[i] = np.partition(chunk, -(drop + 1))[-(drop + 1)] if chunk.size > 1 \
            else float(chunk[0])

    for p in percentiles:
        out[f"chm_p{int(p)}_m"] = quantile_values[p]
    out["chm_p99_m"] = quantile_values[ROBUST_HEIGHT_PERCENTILE]
    out["height_robust_m"] = robust
    out["chm_max_m"] = quantile_values[100.0]
    return out


def vertical_complexity(values: np.ndarray, step_m: float = DEFAULT_VCI_STEP_M) -> float:
    """VCI — вертикальная неоднородность распределения точек по высоте.

    Энтропия Шеннона долей точек по слоям толщиной `step_m`, нормированная на
    максимум `ln(число слоёв)`. 0 — все точки в одном слое, 1 — равномерно.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    span = float(values.max() - values.min())
    bins = max(int(np.ceil(span / step_m)), 1)
    if bins < 2:
        return 0.0
    counts, _ = np.histogram(values, bins=bins)
    share = counts[counts > 0] / counts.sum()
    return float(-(share * np.log(share)).sum() / np.log(bins))


def crown_point_features(
    labels: np.ndarray,
    transform,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    n_trees: int,
    intensity: Optional[np.ndarray] = None,
    return_number: Optional[np.ndarray] = None,
    number_of_returns: Optional[np.ndarray] = None,
    resolution_m: float = 1.0,
    percentiles: tuple = DEFAULT_PERCENTILES,
    vci_step_m: float = DEFAULT_VCI_STEP_M,
) -> dict:
    """Признаки по точкам облака внутри каждой кроны.

    Точка относится к кроне, если её ячейка растра принадлежит этой кроне.

    Args:
        labels: растр меток крон.
        transform: аффинное преобразование растра (`rasterio.Affine`).
        x, y, z: координаты точек облака.
        n_trees: число деревьев.
        intensity: интенсивность отражения — отдельная размерность, не Z.
        return_number: номер возврата.
        number_of_returns: число возвратов в импульсе.
        resolution_m: размер ячейки, м — для плотности точек.
        percentiles: какие квантили считать.
        vci_step_m: толщина слоя для VCI, м.

    Returns:
        Словарь имя признака -> массив длины `n_trees`.
    """
    labels = np.asarray(labels, dtype=np.int64)
    inverse = ~transform
    cols, rows = inverse * (np.asarray(x, dtype=float), np.asarray(y, dtype=float))
    rows = np.floor(np.asarray(rows)).astype(int)
    cols = np.floor(np.asarray(cols)).astype(int)
    inside = ((rows >= 0) & (rows < labels.shape[0])
              & (cols >= 0) & (cols < labels.shape[1]))
    point_label = np.zeros(rows.size, dtype=np.int64)
    point_label[inside] = labels[rows[inside], cols[inside]]
    keep = point_label > 0

    z = np.asarray(z, dtype=float)[keep]
    tree_of_point = point_label[keep]
    counts = np.bincount(tree_of_point, minlength=n_trees + 1)[1:n_trees + 1]

    cell_counts = np.maximum(_counts(labels, n_trees), 1).astype(float)
    out = {
        "n_points": counts.astype(float),
        "point_density_m2": counts / (cell_counts * float(resolution_m) ** 2),
    }

    order = np.argsort(tree_of_point, kind="stable")
    sorted_labels = tree_of_point[order]
    starts = np.searchsorted(sorted_labels, np.arange(1, n_trees + 1), side="left")
    ends = np.searchsorted(sorted_labels, np.arange(1, n_trees + 1), side="right")

    extra = {}
    if intensity is not None:
        extra["intensity"] = np.asarray(intensity, dtype=float)[keep][order]
    if return_number is not None:
        extra["return_number"] = np.asarray(return_number, dtype=float)[keep][order]
    if number_of_returns is not None:
        extra["number_of_returns"] = np.asarray(number_of_returns, dtype=float)[keep][order]
    sorted_z = z[order]

    z_quant = {p: np.full(n_trees, np.nan) for p in percentiles}
    i_quant = {p: np.full(n_trees, np.nan) for p in percentiles}
    vci = np.full(n_trees, np.nan)
    z_mean = np.full(n_trees, np.nan)
    z_std = np.full(n_trees, np.nan)
    i_mean = np.full(n_trees, np.nan)
    i_std = np.full(n_trees, np.nan)
    first_share = np.full(n_trees, np.nan)
    multi_share = np.full(n_trees, np.nan)

    for i, (lo, hi) in enumerate(zip(starts, ends)):
        if hi <= lo:
            continue
        chunk_z = sorted_z[lo:hi]
        z_mean[i], z_std[i] = float(chunk_z.mean()), float(chunk_z.std())
        for p, value in zip(percentiles, np.percentile(chunk_z, list(percentiles))):
            z_quant[p][i] = value
        vci[i] = vertical_complexity(chunk_z, vci_step_m)
        if "intensity" in extra:
            chunk_i = extra["intensity"][lo:hi]
            i_mean[i], i_std[i] = float(chunk_i.mean()), float(chunk_i.std())
            for p, value in zip(percentiles, np.percentile(chunk_i, list(percentiles))):
                i_quant[p][i] = value
        if "return_number" in extra:
            first_share[i] = float((extra["return_number"][lo:hi] == 1).mean())
        if "number_of_returns" in extra:
            multi_share[i] = float((extra["number_of_returns"][lo:hi] > 1).mean())

    out["z_mean_m"] = z_mean
    out["z_std_m"] = z_std
    out["vci"] = vci
    for p in percentiles:
        out[f"z_p{int(p)}_m"] = z_quant[p]
    if intensity is not None:
        out["intensity_mean"] = i_mean
        out["intensity_std"] = i_std
        for p in percentiles:
            out[f"intensity_p{int(p)}"] = i_quant[p]
    if return_number is not None:
        out["first_return_share"] = first_share
    if number_of_returns is not None:
        out["multi_return_share"] = multi_share
    return out


def crown_features(
    labels: np.ndarray,
    chm: np.ndarray,
    transform,
    resolution_m: float,
    n_trees: Optional[int] = None,
    apex_rows: Optional[np.ndarray] = None,
    apex_cols: Optional[np.ndarray] = None,
    points: Optional[dict] = None,
    percentiles: tuple = DEFAULT_PERCENTILES,
    vci_step_m: float = DEFAULT_VCI_STEP_M,
) -> CrownFeatures:
    """Собрать полную таблицу признаков по кронам.

    Args:
        labels: растр меток крон.
        chm: растр высот полога.
        transform: аффинное преобразование растра.
        resolution_m: размер ячейки, м.
        n_trees: число деревьев; None — максимум метки в растре.
        apex_rows, apex_cols: положения вершин для смещения от центроида.
        points: словарь массивов облака — `x`, `y`, `z` обязательны, а
            `intensity`, `return_number`, `number_of_returns` необязательны.
            None — признаки по точкам не считаются.
        percentiles: какие квантили считать.
        vci_step_m: толщина слоя для VCI, м.

    Returns:
        CrownFeatures с колонками по всем группам признаков.
    """
    labels = np.asarray(labels, dtype=np.int64)
    n = int(labels.max()) if n_trees is None else int(n_trees)
    if n <= 0:
        return CrownFeatures(np.empty(0, dtype=int), {})

    columns: dict = {}
    columns.update(crown_geometry(labels, n, resolution_m, apex_rows, apex_cols))
    columns.update(crown_height_structure(labels, chm, n, percentiles))
    if points is not None:
        columns.update(crown_point_features(
            labels, transform, points["x"], points["y"], points["z"], n,
            intensity=points.get("intensity"),
            return_number=points.get("return_number"),
            number_of_returns=points.get("number_of_returns"),
            resolution_m=resolution_m, percentiles=percentiles, vci_step_m=vci_step_m))

    return CrownFeatures(tree_id=np.arange(1, n + 1), columns=columns)
