"""Генерация тестового фикстура: восстановление абсолютных LAS из TLO.

TLO содержит нормализованные Z (HeightAboveGround=0 для ground-точек).
Для теста DSM восстанавливаем абсолютные Z, прибавляя смещение из эталонного DSM.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import laspy
import numpy as np
import rasterio


def restore_absolute_las(
    tlo_path: str,
    reference_dsm_path: str,
    output_las_path: str,
) -> str:
    """Восстановить LAS с абсолютными Z из TLO + эталонного DSM.

    Алгоритм:
    1. Прочитать TLO, взять ground-точки (Classification==2)
    2. Прочитать эталонный DSM
    3. Для каждой ground-точки: Z_absolute = DSM_value(x, y)
    4. Записать LAS с абсолютными Z (ground + vegetation точки получают Z = ground_Z + HAG)

    Args:
        tlo_path: путь к _ground_TLO.las
        reference_dsm_path: путь к эталонному DSM (GeoTIFF)
        output_las_path: путь к выходному LAS с абсолютными Z

    Returns:
        Путь к выходному LAS.
    """
    las = laspy.read(tlo_path)
    cls = np.asarray(las.classification)
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z_hag = np.asarray(las.z, dtype=float)  # HeightAboveGround

    # Прочитать эталонный DSM для получения абсолютных высот ground
    with rasterio.open(reference_dsm_path) as dsm:
        dsm_transform = dsm.transform
        dsm_data = dsm.read(1)
        dsm_nodata = dsm.nodata
        dsm_inv = ~dsm_transform

    # Для каждой точки: получить Z из DSM
    rows, cols = dsm_inv * (x, y)
    rows = rows.astype(int)
    cols = cols.astype(int)

    # Clip to valid range
    h, w = dsm_data.shape
    valid = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)

    z_absolute = np.zeros(len(x), dtype=float)
    if dsm_nodata is not None:
        dsm_valid = dsm_data[rows[valid], cols[valid]]
        # Replace nodata with mean
        dsm_mean = float(np.mean(dsm_data[dsm_data != dsm_nodata]))
        dsm_valid = np.where(dsm_valid == dsm_nodata, dsm_mean, dsm_valid)
    else:
        dsm_valid = dsm_data[rows[valid], cols[valid]]

    z_absolute[valid] = dsm_valid
    z_absolute[~valid] = float(np.mean(dsm_data[dsm_data != dsm_nodata])) if dsm_nodata is not None else float(np.mean(dsm_data))

    # Для ground-точек: Z = DSM value (абсолютная высота земли)
    # Для vegetation-точек: Z = ground_Z + HAG
    ground_mask = cls == 2
    z_absolute[ground_mask] = z_absolute[ground_mask]  # ground Z = DSM value
    veg_mask = ~ground_mask
    # Для vegetation: Z_absolute = ground_Z + HAG
    # Но ground_Z зависит от позиции — используем z_absolute (DSM value) + HAG
    z_absolute[veg_mask] = z_absolute[veg_mask] + z_hag[veg_mask]

    # Записать LAS с абсолютными Z
    out = laspy.create(point_format=las.point_format, file_version=las.header.version)
    out.header = las.header
    out.header.scales = las.header.scales
    out.header.offsets = las.header.offsets

    out.x = x
    out.y = y
    out.z = z_absolute
    out.intensity = las.intensity
    if hasattr(las, "red"):
        out.red = las.red
        out.green = las.green
        out.blue = las.blue
    out.classification = cls
    out.write(output_las_path)

    return output_las_path