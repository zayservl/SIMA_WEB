"""Гауссово сглаживание растра с интерполяцией дырок.

Перед сглаживанием внутренние nodata-дырки заполняются интерполяцией,
чтобы gauss_filter не размыл nodata на валидные пиксели.
Краевые nodata (вне данных) не экстраполируются.
"""

from __future__ import annotations

import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation
from rasterio.fill import fillnodata


def gauss_smooth(
    raster: str,
    smoothed: str,
    sigma: float,
    order: int,
    window_size: int,
    fill_holes: bool = True,
    max_search_distance: int = 100,
) -> None:
    """Гаусс-сглаживание с заполнением внутренних дырок перед фильтром.

    Args:
        raster: входной GeoTIFF
        smoothed: выходной GeoTIFF
        sigma: стандартное отклонение Гаусса
        order: порядок производной (0 = сглаживание)
        window_size: размер окна (для truncate)
        fill_holes: заполнять внутренние nodata-дырки перед сглаживанием
        max_search_distance: радиус интерполяции дырок
    """
    with rasterio.open(raster) as src:
        profile = src.profile
        mask = src.read_masks(1)
        array = src.read(1).astype(float)
        nodata = src.nodata

    if fill_holes and nodata is not None:
        array = _fill_internal_holes(array, mask, nodata, max_search_distance)

    # Заменить оставшийся nodata на медиану валидных, чтобы gauss не разнёс экстремумы
    valid_mask = mask == 255
    if nodata is not None and not np.all(valid_mask):
        fill_val = np.median(array[valid_mask]) if np.any(valid_mask) else 0.0
        work = np.where(valid_mask, array, fill_val)
    else:
        work = array

    truncate = (((window_size - 1) / 2) - 0.5) / sigma if sigma > 0 else 0.0
    smoothed_array = gaussian_filter(input=work, sigma=sigma, order=order, truncate=truncate)

    # Восстановить nodata на краевых пикселях (не экстраполировать)
    if nodata is not None:
        smoothed_array[~valid_mask] = nodata

    with rasterio.open(smoothed, "w", **profile) as dest:
        dest.write_band(1, smoothed_array.astype(profile.get("dtype", "float32")))


def _fill_internal_holes(
    array: np.ndarray, mask: np.ndarray, nodata: float, max_dist: int
) -> np.ndarray:
    """Заполнить только внутренние дырки (не краевые nodata)."""
    was_nodata = (array == nodata)
    valid = mask == 255

    filled = fillnodata(
        array.copy(), mask=mask,
        max_search_distance=max_dist, smoothing_iterations=0)

    dilated_valid = binary_dilation(valid, iterations=1)
    border_mask = np.ones_like(mask, dtype=bool)
    border_mask[1:-1, 1:-1] = False

    holes = was_nodata & dilated_valid & ~border_mask
    keep_nodata = was_nodata & ~holes
    result = np.where(keep_nodata, nodata, filled)
    return result