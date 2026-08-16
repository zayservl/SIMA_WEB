"""Поверхность стоимости для водораздела крон.

Водораздел заливает от маркеров-вершин вверх по подаваемому рельефу, поэтому
граница между кронами проходит там, где рельеф выше. Базовый вариант подаёт
`−CHM`: вершина дерева — дно воронки, седловина между кронами — гребень. Такой
рельеф знает только высоту, и там, где кроны одинаковой высоты соприкасаются,
седловины нет — граница ставится произвольно.

Здесь к нему добавляются карты границ из других источников: перепад высот полога,
цветовые и текстурные границы аэрофотоснимка, перепады интенсивности отражения и
плотности точек. Каждая карта нормируется отдельно и входит со своим весом:

    surface = w_height·norm(−CHM) + w_chm_gradient·norm(|∇CHM|)
            + w_afs_edges·norm(|∇I|) + w_afs_texture·norm(σ_local(I))
            + w_intensity·norm(|∇ITS|) + w_density·norm(|∇DEN|)

Нормировка робастная, по диапазону p1–p99 внутри маски полога: без неё слагаемые
несопоставимы по величине, и одиночный выброс градиента подавляет остальные.

Веса по умолчанию — `w_height=1`, все остальные нули: это в точности базовый
вариант `−CHM`, поэтому подключение модуля само по себе ничего не меняет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import ndimage

from .afs import resample_to_grid


@dataclass
class CostWeights:
    """Веса компонент поверхности стоимости.

    Значения по умолчанию воспроизводят водораздел по голому `−CHM`.
    """

    height: float = 1.0            # norm(−CHM): классическая заливка от вершины
    chm_gradient: float = 0.0      # перепад высот полога — край кроны
    afs_edges: float = 0.0         # цветовые границы снимка
    afs_texture: float = 0.0       # текстурные границы снимка (локальное СКО)
    intensity: float = 0.0         # перепад интенсивности отражения (ITS)
    density: float = 0.0           # перепад плотности точек (DEN)

    def as_dict(self) -> dict:
        return {"height": self.height, "chm_gradient": self.chm_gradient,
                "afs_edges": self.afs_edges, "afs_texture": self.afs_texture,
                "intensity": self.intensity, "density": self.density}

    @property
    def is_height_only(self) -> bool:
        """True, если задействована только высота — базовое поведение."""
        d = self.as_dict()
        return all(v == 0.0 for k, v in d.items() if k != "height")


@dataclass
class CostSurface:
    """Готовая поверхность и вклад каждой компоненты — для отладки и отчёта."""

    surface: np.ndarray
    components: dict = field(default_factory=dict)
    weights: dict = field(default_factory=dict)


def robust_normalize(
    array: np.ndarray,
    mask: Optional[np.ndarray] = None,
    low: float = 1.0,
    high: float = 99.0,
) -> np.ndarray:
    """Привести растр к [0, 1] по перцентилям, устойчиво к выбросам.

    Диапазон берётся по ячейкам `mask` (обычно — маска полога): фон и краевые
    артефакты иначе растягивают шкалу и обнуляют полезный контраст. Значения вне
    диапазона обрезаются. Вырожденный случай (все значения равны) даёт нули.

    Args:
        array: исходный растр.
        mask: где считать перцентили; None — по всему растру.
        low: нижний перцентиль, %.
        high: верхний перцентиль, %.
    """
    work = np.asarray(array, dtype=float)
    finite = np.isfinite(work)
    sample = work[finite & mask] if mask is not None else work[finite]
    if sample.size == 0:
        return np.zeros(work.shape, dtype=float)
    lo, hi = np.percentile(sample, [low, high])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return np.zeros(work.shape, dtype=float)
    out = (np.where(finite, work, lo) - lo) / (hi - lo)
    return np.clip(out, 0.0, 1.0)


def gradient_magnitude(array: np.ndarray) -> np.ndarray:
    """Модуль градиента по Собелю; nodata трактуется как ноль."""
    work = np.asarray(array, dtype=float)
    work = np.where(np.isfinite(work), work, 0.0)
    gy = ndimage.sobel(work, axis=0, mode="nearest")
    gx = ndimage.sobel(work, axis=1, mode="nearest")
    return np.hypot(gy, gx)


def local_std(array: np.ndarray, size: int = 3) -> np.ndarray:
    """Локальное СКО в окне `size` — мера текстуры.

    Считается через E[I²] − E[I]², то есть двумя проходами усредняющего фильтра,
    без поэлементного перебора окон.
    """
    work = np.asarray(array, dtype=float)
    work = np.where(np.isfinite(work), work, 0.0)
    mean = ndimage.uniform_filter(work, size=size, mode="nearest")
    mean_sq = ndimage.uniform_filter(work * work, size=size, mode="nearest")
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Яркость по RGB (Rec. 601). Принимает (3,H,W) или (H,W,3)."""
    arr = np.asarray(rgb, dtype=float)
    if arr.ndim != 3:
        raise ValueError(f"Ожидался трёхканальный растр, получено {arr.shape}")
    if arr.shape[0] == 3 and arr.shape[-1] != 3:
        arr = np.moveaxis(arr, 0, -1)
    return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]


def build_cost_surface(
    chm: np.ndarray,
    weights: Optional[CostWeights] = None,
    afs_rgb: Optional[np.ndarray] = None,
    intensity: Optional[np.ndarray] = None,
    density: Optional[np.ndarray] = None,
    canopy_mask: Optional[np.ndarray] = None,
    texture_window: int = 3,
) -> CostSurface:
    """Собрать поверхность стоимости для водораздела.

    Args:
        chm: растр высот полога, м; nodata — NaN.
        weights: веса компонент; None — только высота (базовое поведение).
        afs_rgb: аэрофотоснимок (3,H,W) или (H,W,3) в своей сетке; приводится
            к сетке ЦМД усреднением.
        intensity: растр интенсивности отражения (ITS) в сетке ЦМД.
        density: растр плотности точек (DEN) в сетке ЦМД.
        canopy_mask: где нормировать компоненты; None — вся площадь.
        texture_window: окно локального СКО для текстуры, px.

    Returns:
        CostSurface с итоговой поверхностью и вкладами компонент.

    Raises:
        ValueError: если задан вес на компоненту, для которой нет данных, —
            молчаливое обнуление скрыло бы отсутствие снимка или канала.
    """
    weights = weights or CostWeights()
    work = np.asarray(chm, dtype=float)
    shape = work.shape
    mask = canopy_mask if canopy_mask is not None else np.ones(shape, dtype=bool)

    components: dict = {}
    if weights.height:
        # Высота нормируется без обрезки (0–100 %), в отличие от карт границ:
        # обрезка по перцентилям склеила бы макушки самых высоких крон в плато,
        # а водораздел различает ячейки только по порядку значений. Монотонное
        # преобразование порядок сохраняет — заливка остаётся прежней.
        components["height"] = robust_normalize(-work, mask, low=0.0, high=100.0)
    if weights.chm_gradient:
        components["chm_gradient"] = robust_normalize(gradient_magnitude(work), mask)

    needs_afs = weights.afs_edges or weights.afs_texture
    if needs_afs:
        if afs_rgb is None:
            raise ValueError("Задан вес на границы или текстуру АФС, но снимок не передан")
        lum = resample_to_grid(luminance(afs_rgb), shape, how="mean")
        if weights.afs_edges:
            components["afs_edges"] = robust_normalize(gradient_magnitude(lum), mask)
        if weights.afs_texture:
            components["afs_texture"] = robust_normalize(
                local_std(lum, texture_window), mask)

    for name, raster, weight in (("intensity", intensity, weights.intensity),
                                 ("density", density, weights.density)):
        if not weight:
            continue
        if raster is None:
            raise ValueError(f"Задан вес на компоненту {name!r}, но растр не передан")
        resampled = resample_to_grid(np.asarray(raster, dtype=float), shape, how="mean")
        components[name] = robust_normalize(gradient_magnitude(resampled), mask)

    used = weights.as_dict()
    surface = np.zeros(shape, dtype=float)
    for name, component in components.items():
        surface += used[name] * component

    return CostSurface(surface=surface, components=components,
                       weights={k: v for k, v in used.items() if v})
