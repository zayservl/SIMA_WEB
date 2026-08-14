"""Гауссово сглаживание растра.

Порт из legacy `processings/raster_utils.py::gauss_smooth`.
Legacy: gauss_filter → nodata restore. Без предварительной интерполяции дырок.
Опционально: интерполяция внутренних дырок перед сглаживанием (fill_holes=True).
"""

from __future__ import annotations

import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter

from .holes import fill_voids


def gauss_smooth(
    raster: str,
    smoothed: str,
    sigma: float,
    order: int,
    window_size: int,
    fill_holes: bool = False,
    max_search_distance: int = 100,
    max_extrapolation_px: float = 0.0,
    fill_passes: int = 3,
    fill_method: str = "laplace",
) -> None:
    with rasterio.open(raster) as src:
        profile = src.profile
        mask = src.read_masks(1)
        array = src.read(1).astype(float)
        nodata = src.nodata

    valid_mask = mask == 255

    if fill_holes and nodata is not None:
        result = fill_voids(
            array, valid_mask,
            method=fill_method,
            max_search_distance=max_search_distance,
            smoothing_iterations=0,
            max_extrapolation_px=max_extrapolation_px,
            max_passes=fill_passes,
        )
        array = result.array
        valid_mask = valid_mask | result.filled

    fill_val = np.median(array[valid_mask]) if np.any(valid_mask) else 0.0
    work = np.where(valid_mask, array, fill_val)

    truncate = (((window_size - 1) / 2) - 0.5) / sigma if sigma > 0 else 0.0
    smoothed_array = gaussian_filter(input=work, sigma=sigma, order=order, truncate=truncate)

    if nodata is not None:
        smoothed_array[~valid_mask] = nodata

    with rasterio.open(smoothed, "w", **profile) as dest:
        dest.write_band(1, smoothed_array.astype(profile.get("dtype", "float32")))
