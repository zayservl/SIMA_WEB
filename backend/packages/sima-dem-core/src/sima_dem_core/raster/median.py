"""Медианный фильтр.

Порт из legacy `processings/median_filter.py`.

Использует scipy.ndimage.median_filter(mode="nearest") вместо исходного
scipy.signal.medfilt: medfilt дополняет край растра нулями, из-за чего в углах
и на границе окно фильтра оказывается в основном заполнено нулевым паддингом
и валидные краевые пиксели ошибочно помечаются как nodata (см. mask_filtered
ниже). mode="nearest" продолжает граничные значения растра, что не искажает
маску валидности у края.
"""

from __future__ import annotations

import os
import rasterio
from scipy.ndimage import median_filter
import numpy as np


def med_filter(image_path: str, window: int) -> None:
    """Применить медианный фильтр к GeoTIFF (in-place замена).

    Args:
        image_path: путь к GeoTIFF (будет перезаписан)
        window: размер окна медианного фильтра (нечётное)
    """
    filename, extent = os.path.splitext(image_path)
    output_file_path = filename + "_filtered" + extent
    with rasterio.open(image_path) as original:
        kwds = original.profile
        mask = original.read_masks(1)
        val = original.nodata

        arr_data = original.read(1).astype(float)
        if val is not None:
            arr_data[arr_data == val] = 0
            arr_no_nd = arr_data.flatten()[arr_data.flatten() != val]
        else:
            arr_no_nd = arr_data.flatten()

        shape = arr_data.shape
        arr_flat = arr_data.flatten()
        if val is not None:
            arr_flat = np.where(arr_flat == val, np.median(arr_no_nd), arr_flat)
        arr_data = arr_flat.reshape(shape)

        filtered_data = median_filter(arr_data.copy(), size=int(window), mode="nearest")
        mask_filtered = median_filter(mask.copy().astype(float), size=int(window), mode="nearest")

        for i in range(mask_filtered.shape[0]):
            for j in range(mask_filtered.shape[1]):
                if mask_filtered[i, j] < 255:
                    filtered_data[i, j] = original.nodata if original.nodata is not None else -9999.0

        with rasterio.open(output_file_path, "w", **kwds) as dst:
            dst.write(filtered_data.astype(kwds.get("dtype", "float32")), 1)

    os.remove(image_path)
    os.rename(output_file_path, image_path)