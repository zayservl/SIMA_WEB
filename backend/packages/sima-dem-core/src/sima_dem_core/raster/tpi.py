"""TPI — индекс топографического положения.

Порт из legacy `relief_analysis/tpi.py`. Без OpenCV — numpy вместо cv2.blur.
Трёхмасштабный TPI: радиусы 270, 810, 2430 м.
"""

from __future__ import annotations

import os
from pathlib import Path

import rasterio
import numpy as np
from osgeo import gdal


def calculate_tpi(
    dem_path: str,
    crs: str,
    output_folder: str,
    input_res: float,
    res: float,
) -> str:
    """Рассчитать трёхмасштабный TPI из ЦМР.

    Args:
        dem_path: путь к ЦМР (_dem.tif)
        crs: CRS (WKT-строка)
        output_folder: каталог для выходного TPI
        input_res: разрешение входного растра (м)
        res: разрешение выходного TPI (м)

    Returns:
        Путь к выходному TPI-растру.
    """
    r1 = int(270 / input_res)
    r2 = int(810 / input_res)
    r3 = int(2430 / input_res)
    radii = [r1, r2, r3]

    stem = Path(dem_path).stem.replace("_dem", "")
    output_path = os.path.join(output_folder, stem + "_tpi.tif")

    with rasterio.open(dem_path) as original:
        kwds = original.profile
        mask = original.read_masks(1)
        val = original.nodata
        arr_data = original.read(1).astype(float)

        arr_no_nd = arr_data.flatten()
        if val is not None:
            arr_no_nd = arr_no_nd[arr_no_nd != val]
        std = float(np.std(arr_no_nd)) if len(arr_no_nd) > 0 else 1.0

        blurred_list = []
        for r in radii:
            if r <= 0:
                r = 1
            # numpy box blur (эквивалент cv2.blur)
            kernel = np.ones((r, r)) / (r * r)
            from scipy.ndimage import uniform_filter
            blurred = uniform_filter(arr_data.copy(), size=r)
            blurred_list.append(-blurred + arr_data.copy())

        if std == 0:
            std = 1.0
        filtered_data = (blurred_list[0] + blurred_list[1] + blurred_list[2]) / std / 3.0

        for i in range(mask.shape[0]):
            for j in range(mask.shape[1]):
                if mask[i, j] < 255:
                    filtered_data[i, j] = val if val is not None else -9999.0

    with rasterio.open(output_path, "w", **kwds) as dst:
        dst.write(filtered_data.astype(np.float32), 1)

    # Перевыборка к заданному разрешению
    infn = output_path.replace("_tpi.tif", "_tpi_tmp.tif")
    os.rename(output_path, infn)
    try:
        ds = gdal.Warp(output_path, infn, resampleAlg="near", xRes=res, yRes=res)
        ds = gdal.Open(output_path, gdal.GA_Update)
        if ds is not None:
            ds.SetProjection(crs)
            ds = None
    except Exception as ee:  # noqa: BLE001
        print("gdal Warp/SetProjection failed:", ee)
    finally:
        ds = None
        if os.path.exists(infn):
            os.remove(infn)

    return output_path