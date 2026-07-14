"""Гауссово сглаживание растра с интерполяцией дырок.

Правило: DTM строится с пустотами (nodata). При сглаживании внутренние дырки
интерполируются (заполняются), но экстраполяция краёв недопустима.

Различие дырка vs край:
  - Дырка: nodata-пиксель, окружённый валидными данными со всех сторон.
  - Край: nodata-пиксель, примыкающий к границе области данных снаружи.

Определение через connected components: nodata-пиксели, касающиеся
границы растра, — это край (не экстраполировать). Остальные — дырки.
"""

from __future__ import annotations

import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter, label, binary_fill_holes
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
    """Гаусс-сглаживание с интерполяцией внутренних дырок.

    DTM может иметь nodata-пустоты. Перед сглаживанием:
    1. Внутренние дырки (nodata, окружённые валидными) интерполируются.
    2. Краевые nodata (примыкающие к границе данных) остаются.
    3. gauss_filter применяется к массиву без экстремальных nodata.
    4. После gauss — краевые nodata восстанавливаются.
    """
    with rasterio.open(raster) as src:
        profile = src.profile
        mask = src.read_masks(1)
        array = src.read(1).astype(float)
        nodata = src.nodata

    valid_mask = mask == 255

    if fill_holes and nodata is not None:
        holes_mask = _find_internal_holes(valid_mask)
        if np.any(holes_mask):
            filled = fillnodata(
                array.copy(),
                mask=mask,
                max_search_distance=max_search_distance,
                smoothing_iterations=0,
            )
            array = np.where(holes_mask, filled, array)
            valid_mask = valid_mask | holes_mask

    fill_val = np.median(array[valid_mask]) if np.any(valid_mask) else 0.0
    work = np.where(valid_mask, array, fill_val)

    truncate = (((window_size - 1) / 2) - 0.5) / sigma if sigma > 0 else 0.0
    smoothed_array = gaussian_filter(input=work, sigma=sigma, order=order, truncate=truncate)

    if nodata is not None:
        smoothed_array[~valid_mask] = nodata

    with rasterio.open(smoothed, "w", **profile) as dest:
        dest.write_band(1, smoothed_array.astype(profile.get("dtype", "float32")))


def _find_internal_holes(valid_mask: np.ndarray) -> np.ndarray:
    """Найти внутренние дырки — nodata, окружённые валидными данными.

    Использует binary_fill_holes: заполляет дырки в валидной маске,
    потом вычитает исходную маску — разница и есть дырки.
    Краевые nodata (касаются границы растра) не считаются дырками.
    """
    filled = binary_fill_holes(valid_mask)
    holes = filled & ~valid_mask
    return holes