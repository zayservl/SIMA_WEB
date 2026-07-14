"""Гауссово сглаживание растра.

Порт из legacy `processings/raster_utils.py::gauss_smooth`.
Без OpenCV — scipy.ndimage.gaussian_filter.
"""

from __future__ import annotations

import rasterio
import numpy as np
from scipy.ndimage import gaussian_filter


def gauss_smooth(raster: str, smoothed: str, sigma: float, order: int, window_size: int) -> None:
    """Применить гауссов фильтр к GeoTIFF с сохранением nodata-маски.

    Args:
        raster: входной GeoTIFF
        smoothed: выходной GeoTIFF
        sigma: стандартное отклонение Гаусса
        order: порядок производной (0 = сглаживание)
        window_size: размер окна (для truncate)
    """
    with rasterio.open(raster) as src:
        profile = src.profile
        mask = src.read_masks(1)
        array = src.read(1)

    truncate = (((window_size - 1) / 2) - 0.5) / sigma if sigma > 0 else 0.0
    smoothed_array = gaussian_filter(input=array.astype(float), sigma=sigma, order=order, truncate=truncate)

    for i in range(mask.shape[0]):
        for j in range(mask.shape[1]):
            if mask[i, j] < 255:
                smoothed_array[i, j] = src.nodata if src.nodata is not None else -9999.0

    with rasterio.open(smoothed, "w", **profile) as dest:
        dest.write_band(1, smoothed_array.astype(profile.get("dtype", "float32")))