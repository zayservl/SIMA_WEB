"""TPI — индекс топографического положения.

Радиусы инкапсулированы в TPIConfig. Без хардкода.
Трёхмасштабный TPI: настраиваемые радиусы (по умолчанию 270, 810, 2430 м).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import rasterio
import numpy as np
from osgeo import gdal
from scipy.ndimage import uniform_filter


@dataclass
class TPIConfig:
    """Параметры TPI."""
    radii_m: list = field(default_factory=lambda: [270, 810, 2430])
    res: float = 10.0
    fill_holes: bool = True
    max_search_distance: int = 100


def calculate_tpi(
    dem_path: str,
    crs: str,
    output_folder: str,
    input_res: float,
    res: float,
    config: TPIConfig | None = None,
) -> str:
    """Рассчитать трёхмасштабный TPI из ЦМР.

    Args:
        dem_path: путь к ЦМР (_dem.tif или _dem_smooth.tif)
        crs: CRS (WKT-строка)
        output_folder: каталог для выходного TPI
        input_res: разрешение входного растра (м)
        res: разрешение выходного TPI (м)
        config: параметры TPI (радиусы, интерполяция)

    Returns:
        Путь к выходному TPI-растру.
    """
    cfg = config or TPIConfig(res=res)
    radii = [max(int(r / input_res), 1) for r in cfg.radii_m]

    stem = Path(dem_path).stem.replace("_dem", "").replace("_smooth", "")
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
            blurred = uniform_filter(arr_data.copy(), size=r)
            blurred_list.append(-blurred + arr_data.copy())

        if std == 0:
            std = 1.0
        filtered_data = sum(blurred_list) / std / 3.0

        if val is not None:
            for i in range(mask.shape[0]):
                for j in range(mask.shape[1]):
                    if mask[i, j] < 255:
                        filtered_data[i, j] = val

    with rasterio.open(output_path, "w", **kwds) as dst:
        dst.write(filtered_data.astype(np.float32), 1)

    infn = output_path.replace("_tpi.tif", "_tpi_tmp.tif")
    os.rename(output_path, infn)
    try:
        ds = gdal.Warp(output_path, infn, resampleAlg="near", xRes=cfg.res, yRes=cfg.res)
        ds = gdal.Open(output_path, gdal.GA_Update)
        if ds is not None:
            ds.SetProjection(crs)
            ds = None
    except Exception as ee:
        print("gdal Warp/SetProjection failed:", ee)
    finally:
        ds = None
        if os.path.exists(infn):
            os.remove(infn)

    return output_path