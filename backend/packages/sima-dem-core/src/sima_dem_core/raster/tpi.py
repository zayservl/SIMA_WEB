"""TPI — индекс топографического положения (многомасштабный).

Порт из legacy `relief_analysis/tpi.py`.
Три масштаба (270/810/2430 м), box-filter (cv2.blur), нормализация по std.
Формула: TPI = mean(DEM - blur_r(DEM)) / std(DEM) / 3
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import rasterio
import numpy as np
from osgeo import gdal


@dataclass
class TPIConfig:
    radii_m: list = field(default_factory=lambda: [270, 810, 2430])
    res: float = 10.0


def calculate_tpi(
    dem_path: str,
    crs: str,
    output_folder: str,
    input_res: float,
    res: float,
    config: TPIConfig | None = None,
) -> str:
    cfg = config or TPIConfig(res=res)
    radii_px = [max(int(r / input_res), 1) for r in cfg.radii_m]

    stem = Path(dem_path).stem.replace("_dem", "").replace("_smooth", "")
    output_path = os.path.join(output_folder, stem + "_tpi.tif")

    with rasterio.open(dem_path) as src:
        profile = src.profile
        mask = src.read_masks(1)
        nodata = src.nodata
        arr = src.read(1).astype(float)

        valid_vals = arr.flatten()
        if nodata is not None:
            valid_vals = valid_vals[valid_vals != nodata]
        std = float(np.std(valid_vals)) if len(valid_vals) > 0 else 1.0
        if std == 0:
            std = 1.0

        global_mean = float(np.mean(valid_vals)) if len(valid_vals) > 0 else 0.0
        if nodata is not None:
            arr = np.where(arr == nodata, global_mean, arr)

        tpi_sum = np.zeros_like(arr)
        for r in radii_px:
            blurred = cv2.blur(arr.copy(), (r, r))
            tpi_sum += (arr - blurred)

        tpi = tpi_sum / std / len(radii_px)

        if nodata is not None:
            tpi[mask < 255] = nodata

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(tpi.astype(np.float32), 1)

    tmp = output_path.replace("_tpi.tif", "_tpi_tmp.tif")
    os.rename(output_path, tmp)
    try:
        gdal.Warp(output_path, tmp, resampleAlg="near", xRes=cfg.res, yRes=cfg.res)
        ds = gdal.Open(output_path, gdal.GA_Update)
        if ds is not None:
            ds.SetProjection(crs)
            ds = None
    except Exception as ee:
        print("gdal Warp/SetProjection failed:", ee)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    return output_path