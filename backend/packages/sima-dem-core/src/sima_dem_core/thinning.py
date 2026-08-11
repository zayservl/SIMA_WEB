"""Пространственное прореживание точек по минимальному расстоянию.

Аналог PDAL `filters.sample` (Poisson dart-throwing): из облака отбирается
подмножество, в котором никакие две точки не ближе заданного расстояния.

Отбор двухэтапный — иначе жадный проход по миллионам точек в чистом Python
неприемлемо медленный:
  1. решётка с ячейкой d: из каждой ячейки берётся первая точка (быстро,
     векторизовано, сразу сокращает облако до ~площадь/d²);
  2. жадный проход по кандидатам с проверкой соседних ячеек — точки у общих
     границ ячеек могут оказаться ближе d, их отбрасываем.

Результат — корректное прореживание (все пары дальше d), но не максимальное
по мощности; PDAL даёт такую же гарантию.
"""

from __future__ import annotations

import numpy as np


def thin_by_min_distance(x: np.ndarray, y: np.ndarray, min_distance: float) -> np.ndarray:
    """Индексы точек, отстоящих друг от друга не ближе min_distance.

    Args:
        x, y: плановые координаты точек в единицах СК (метры).
        min_distance: минимальное расстояние между точками, м. 0 или
            отрицательное — прореживание не выполняется.

    Returns:
        Массив индексов сохранённых точек в порядке возрастания.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size == 0:
        return np.empty(0, dtype=int)
    if not min_distance or min_distance <= 0:
        return np.arange(x.size)

    cell = float(min_distance)
    ix = np.floor(x / cell).astype(np.int64)
    iy = np.floor(y / cell).astype(np.int64)

    # Этап 1: по одной точке на ячейку d×d.
    _, first = np.unique(np.stack([ix, iy], axis=1), axis=0, return_index=True)
    candidates = np.sort(first)

    # Этап 2: точная проверка расстояний между кандидатами из соседних ячеек.
    limit = cell * cell
    kept: list[int] = []
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for i in candidates:
        px, py, cx, cy = x[i], y[i], ix[i], iy[i]
        too_close = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for qx, qy in grid.get((cx + dx, cy + dy), ()):
                    if (qx - px) ** 2 + (qy - py) ** 2 < limit:
                        too_close = True
                        break
                if too_close:
                    break
            if too_close:
                break
        if not too_close:
            grid.setdefault((cx, cy), []).append((px, py))
            kept.append(int(i))

    return np.asarray(kept, dtype=int)
