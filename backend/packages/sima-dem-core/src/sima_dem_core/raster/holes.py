"""Заполнение пустот растра высот.

Общий модуль для ЦМР (`sima_dem_ground.ground`), ЦММ (`sima_dem_dsm.dsm`) и
сглаживания (`sima_dem_core.raster.smooth`).

Что считается пустотой под заполнение — `fillable_mask`:

* внутренние дыры, полностью окружённые данными (`binary_fill_holes`);
* ячейки не далее `max_extrapolation_px` от данных.

Второе правило добавлено потому, что чисто топологический критерий выбрасывал
любую пустоту, касающуюся рамки растра, даже вплотную к данным: на тайле
P-42-042-249-a бенчмарка — 76 % растра при 23 % валидных ячеек. Область, куда
съёмка не заходила вовсе, при этом остаётся пустой намеренно: заполнять её
значило бы придумывать рельеф. Глубину допустимой экстраполяции задаёт вызывающий.

Чем заполняется — `fill_voids`, два метода:

* ``"laplace"`` — решение уравнения Лапласа с граничными условиями по данным
  (гармоническая, она же «мембранная», интерполяция). Поверхность гладкая по
  построению и подчиняется принципу максимума: значения внутри пустоты не выходят
  за пределы значений на её границе.
* ``"idw"`` — `GDALFillNodata`: обратные расстояния по коническому поиску в
  восьми направлениях. Быстрее, но даёт характерные радиальные лучи от границы
  внутрь крупных пустот и не дотягивается дальше `max_search_distance`.

Заполнение многопроходное: часть пустот становится внутренними дырами только
ПОСЛЕ заполнения соседних (см. `fill_voids`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sparse
import scipy.sparse.linalg as sparse_linalg
from rasterio.fill import fillnodata
from scipy.ndimage import binary_fill_holes, distance_transform_edt

from .hydro import MIN_WATER_AREA_M2, WaterFlattening, flatten_water_voids

# Больше этого числа ячеек связная пустота решается не Лапласом, а IDW: прямое
# разложение разреженной системы такого размера становится дороже пользы.
LAPLACE_MAX_CELLS = 500_000

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


@dataclass
class VoidFill:
    """Результат заполнения пустот растра."""

    array: np.ndarray                                   # растр с заполненными пустотами
    filled: np.ndarray                                  # маска заполненных ячеек
    water: np.ndarray                                   # маска гидровыравненных ячеек
    water_levels: list[float] = field(default_factory=list)   # отметки водоёмов, м
    passes: int = 0                                     # сколько проходов реально выполнено


def fillable_mask(valid: np.ndarray, max_extrapolation_px: float = 0.0) -> np.ndarray:
    """Маска ячеек nodata, которые следует заполнить.

    Args:
        valid: булева маска валидных (не-nodata) ячеек растра.
        max_extrapolation_px: максимальное расстояние в пикселях, на которое
            допускается экстраполяция за границу валидной области. 0 — только
            внутренние дыры.

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


def fill_voids(
    array: np.ndarray,
    valid: np.ndarray,
    method: str = "laplace",
    max_search_distance: int = 100,
    smoothing_iterations: int = 0,
    max_extrapolation_px: float = 0.0,
    max_passes: int = 3,
    resolution_m: float = 1.0,
    hydro_flatten: bool = False,
    min_water_area_m2: float | None = None,
    water: np.ndarray | None = None,
) -> VoidFill:
    """Заполнить пустоты растра, не изменяя валидные ячейки.

    Заполнение повторяется, пока очередной проход добавляет ячейки. Один проход
    оставляет незаполненными пустоты, которые становятся внутренними дырами
    только ПОСЛЕ заполнения соседних: маска считается до заполнения, поэтому
    водоём, сообщавшийся с внешней пустотой узкой протокой, замыкается
    заполнением этой протоки и остаётся дырой.

    Наружу область данных при этом не разрастается: допуск
    `max_extrapolation_px` считается один раз от ИСХОДНОЙ валидной маски, а
    последующие проходы добавляют только внутренние дыры. Иначе каждый проход
    отодвигал бы границу ещё на `max_extrapolation_px`.

    Гарантия: `out[valid] == array[valid]` поэлементно при любых настройках —
    исходные измерения не переинтерполируются и не сглаживаются.

    Args:
        array: значения растра (в пустотах — nodata).
        valid: булева маска валидных ячеек.
        method: ``"laplace"`` (гармоническая интерполяция, без лучей) или
            ``"idw"`` (`GDALFillNodata`, историческое поведение).
        max_search_distance: радиус поиска для ``"idw"``, px.
        smoothing_iterations: сглаживание заполненных значений для ``"idw"``.
        max_extrapolation_px: допустимая экстраполяция за границу данных, px.
        max_passes: максимум проходов; 1 — однопроходное поведение.
        resolution_m: размер ячейки, м — нужен для порога площади водоёма.
        hydro_flatten: выравнивать ли пустоты-водоёмы плоской отметкой вместо
            интерполяции (см. `sima_dem_core.raster.hydro`).
        min_water_area_m2: порог площади водоёма; None — порог 3DEP (0.8 га).
        water: готовая маска водоёмов; если задана, эвристический отбор не
            выполняется.

    Returns:
        VoidFill: растр, маска заполненных ячеек, маска гидровыравненных ячеек,
        их отметки и число выполненных проходов.
    """
    array = np.asarray(array)
    valid = np.asarray(valid, dtype=bool)
    work = array.copy()
    filled = np.zeros(array.shape, dtype=bool)
    flattened = np.zeros(array.shape, dtype=bool)
    levels: list[float] = []

    # Наружный допуск фиксируем по исходным данным — он не должен нарастать с проходами.
    edge_allowance = fillable_mask(valid, max_extrapolation_px)

    done_passes = 0
    for _ in range(max(1, int(max_passes))):
        current = valid | filled
        targets = (fillable_mask(current) | edge_allowance) & ~current
        if not targets.any():
            break
        done_passes += 1

        if hydro_flatten:
            flat = flatten_water_voids(
                work, current, targets, resolution_m,
                water=water,
                min_area_m2=(MIN_WATER_AREA_M2 if min_water_area_m2 is None
                             else min_water_area_m2),
            )
            if flat.water.any():
                work = flat.array
                flattened |= flat.water
                filled |= flat.water
                levels.extend(flat.levels)
                targets &= ~flat.water
                current = valid | filled

        new = _interpolate(work, current, targets, method,
                           max_search_distance, smoothing_iterations)
        if not new.any():
            break
        filled |= new

    work[valid] = array[valid]      # жёсткая гарантия неизменности исходных ячеек
    return VoidFill(work, filled, flattened, levels, done_passes)


def _interpolate(
    work: np.ndarray,
    valid: np.ndarray,
    targets: np.ndarray,
    method: str,
    max_search_distance: int,
    smoothing_iterations: int,
) -> np.ndarray:
    """Заполнить `targets` выбранным методом, изменив `work` на месте.

    Returns:
        Маска ячеек, которые действительно получили значение: за
        `max_search_distance` метод ``"idw"`` не дотягивается и оставляет nodata.
    """
    if not targets.any():
        return np.zeros(work.shape, dtype=bool)
    if method == "laplace":
        candidate = _fill_laplace(work, valid, targets,
                                  max_search_distance, smoothing_iterations)
    elif method == "idw":
        candidate = _fill_idw(work, valid, max_search_distance, smoothing_iterations)
    else:
        raise ValueError(f"неизвестный метод заполнения пустот: {method!r}")
    new = targets & (candidate != work)
    work[new] = candidate[new]
    return new


def _fill_idw(
    work: np.ndarray,
    valid: np.ndarray,
    max_search_distance: int,
    smoothing_iterations: int,
) -> np.ndarray:
    """`GDALFillNodata`: обратные расстояния по коническому поиску."""
    return fillnodata(
        work.copy(),
        mask=np.where(valid, 255, 0).astype("uint8"),
        max_search_distance=max_search_distance,
        smoothing_iterations=smoothing_iterations,
    )


def _fill_laplace(
    work: np.ndarray,
    valid: np.ndarray,
    targets: np.ndarray,
    max_search_distance: int,
    smoothing_iterations: int,
) -> np.ndarray:
    """Гармоническая интерполяция: решение уравнения Лапласа в пустотах.

    Для каждой связной пустоты решается разреженная система пятиточечной схемы
    ∇²u = 0 с условиями Дирихле по валидным соседям и Неймана (нулевой поток) на
    рамке растра. Результат гладкий по построению — радиальных лучей, характерных
    для конического IDW, не возникает; принцип максимума не даёт значениям выйти
    за диапазон границы пустоты.

    Все пустоты растра решаются ОДНОЙ системой: они между собой не соприкасаются,
    поэтому матрица блочно-диагональна и результат тот же, что при раздельном
    решении, а накладные расходы платятся один раз. На реальной ЦМР это важно:
    типичный тайл даёт больше десяти тысяч мелких пустот, и по отдельности они
    решались бы в разы дольше самого счёта.

    Если пустот больше `LAPLACE_MAX_CELLS`, растр заполняется методом ``"idw"``:
    прямое разложение системы такого размера обходится дороже выигрыша.
    """
    cells = np.argwhere(targets)
    if len(cells) > LAPLACE_MAX_CELLS:
        return _fill_idw(work, valid, max_search_distance, smoothing_iterations)

    out = work.astype("float64", copy=True)
    height, width = out.shape
    size = len(cells)
    rows, cols = cells[:, 0], cells[:, 1]

    # Номер ячейки в системе; -1 — ячейка не входит в неё.
    number = np.full(out.shape, -1, dtype=np.int64)
    number[rows, cols] = np.arange(size)

    degree = np.zeros(size)
    rhs = np.zeros(size)
    off_rows: list[np.ndarray] = []
    off_cols: list[np.ndarray] = []

    # Диагональ — число соседей внутри растра, внедиагональные −1 — соседи-пустоты,
    # правая часть — значения валидных соседей (Дирихле). Соседи за рамкой растра
    # не учитываются, что равносильно условию Неймана.
    for dr, dc in _NEIGHBOURS:
        rr, cc = rows + dr, cols + dc
        inside = (rr >= 0) & (rr < height) & (cc >= 0) & (cc < width)
        k = np.flatnonzero(inside)
        rr, cc = rr[inside], cc[inside]

        dirichlet = valid[rr, cc]
        np.add.at(degree, k[dirichlet], 1.0)
        np.add.at(rhs, k[dirichlet], out[rr[dirichlet], cc[dirichlet]])

        neighbour = number[rr, cc]
        internal = ~dirichlet & (neighbour >= 0)
        np.add.at(degree, k[internal], 1.0)
        off_rows.append(k[internal])
        off_cols.append(neighbour[internal])

    # Ячейка без единого соседа (изолированная) не имеет уравнения: оставляем как есть.
    isolated = degree == 0
    rhs[isolated] = out[rows[isolated], cols[isolated]]

    diagonal = np.arange(size)
    matrix = sparse.csr_matrix(
        (np.concatenate([-np.ones(sum(map(len, off_rows))), np.maximum(degree, 1.0)]),
         (np.concatenate(off_rows + [diagonal]),
          np.concatenate(off_cols + [diagonal]))),
        shape=(size, size))
    out[rows, cols] = sparse_linalg.spsolve(matrix, rhs)
    return out.astype(work.dtype, copy=False)


__all__ = [
    "VoidFill",
    "WaterFlattening",
    "MIN_WATER_AREA_M2",
    "LAPLACE_MAX_CELLS",
    "fillable_mask",
    "px_from_metres",
    "fill_voids",
    "flatten_water_voids",
]
