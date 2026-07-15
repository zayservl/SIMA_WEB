"""Вывод векторных слоёв в ESRI Shapefile (.shp).

Требование Q3: отметки высот — .shp, горизонтали — .shp (см. processings/relief.txt).
Горизонтали пишет sima_dem_core.raster.contours.generate_contours (driver
выбирается там); здесь — точки высот (3D) в .shp через OGR, по образцу contours.py.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np
from osgeo import ogr, osr


def _layer_name(out_path: str) -> str:
    """Имя слоя для ESRI Shapefile ≤ 10 символов (ограничение DBF)."""
    stem = os.path.splitext(os.path.basename(out_path))[0]
    return stem[:10] if len(stem) > 10 else stem


def write_points_shp(
    points_xyz: np.ndarray,
    out_path: str,
    crs_wkt: Optional[str] = None,
    field_name: str = "alt",
) -> str:
    """Записать 3D-точки в .shp. points_xyz: (N,3) [x,y,z]. Поле field_name = z."""
    pts = np.asarray(points_xyz, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError(f"Ожидался (N,3) массив, получено {pts.shape}")

    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)

    driver = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(out_path):
        driver.DeleteDataSource(out_path)
    ds = driver.CreateDataSource(out_path)

    srs = None
    if crs_wkt:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(crs_wkt)
    layer = ds.CreateLayer(_layer_name(out_path), srs=srs, geom_type=ogr.wkbPoint25D)
    layer.CreateField(ogr.FieldDefn(field_name, ogr.OFTReal))

    for row in pts:
        feat = ogr.Feature(layer.GetLayerDefn())
        feat.SetField(field_name, float(row[2]))
        pt = ogr.Geometry(ogr.wkbPoint25D)
        pt.AddPoint(float(row[0]), float(row[1]), float(row[2]))
        feat.SetGeometry(pt)
        layer.CreateFeature(feat)
        feat = None

    ds = None  # закрыть и сбросить на диск
    return out_path