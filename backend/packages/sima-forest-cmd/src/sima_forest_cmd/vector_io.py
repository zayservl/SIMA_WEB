"""Запись деревьев и крон в ESRI Shapefile через OGR.

Собственный писатель, а не `sima_relief_service.shp_io`: тот принимает ровно одно
атрибутивное поле, а дереву нужны высота, площадь кроны и диаметр, — и,
главное, библиотека не должна зависеть от сервисного слоя.

Имена полей ограничены 10 символами — предел формата DBF.
"""

from __future__ import annotations

import json
import os
from typing import Mapping, Optional, Sequence

import numpy as np
from osgeo import ogr, osr

_OGR_TYPE = {
    "f": ogr.OFTReal,
    "i": ogr.OFTInteger,
}


def _layer_name(out_path: str) -> str:
    """Имя слоя для shapefile: не длиннее 10 символов (ограничение DBF)."""
    stem = os.path.splitext(os.path.basename(out_path))[0]
    return stem[:10]


def _create(out_path: str, crs_wkt: Optional[str], geom_type):
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
    layer = ds.CreateLayer(_layer_name(out_path), srs=srs, geom_type=geom_type)
    return ds, layer


def _add_fields(layer, attributes: Mapping[str, np.ndarray]) -> list:
    names = []
    for name, values in attributes.items():
        field = name[:10]
        kind = np.asarray(values).dtype.kind
        layer.CreateField(ogr.FieldDefn(field, _OGR_TYPE.get(kind, ogr.OFTReal)))
        names.append(field)
    return names


def write_tree_points(
    xy: np.ndarray,
    out_path: str,
    crs_wkt: Optional[str] = None,
    attributes: Optional[Mapping[str, np.ndarray]] = None,
) -> str:
    """Записать вершины деревьев в .shp (3D-точки).

    Args:
        xy: (N,3) — x, y, высота. Высота идёт и в Z геометрии.
        out_path: путь к .shp.
        crs_wkt: СК слоя.
        attributes: атрибуты по именам полей, массивы длины N.

    Returns:
        Путь к созданному файлу.
    """
    pts = np.asarray(xy, dtype=float)
    if pts.ndim != 2 or pts.shape[1] < 3:
        raise ValueError(f"Ожидался массив (N,3), получено {pts.shape}")

    attributes = attributes or {}
    ds, layer = _create(out_path, crs_wkt, ogr.wkbPoint25D)
    fields = _add_fields(layer, attributes)
    values = [np.asarray(v) for v in attributes.values()]

    defn = layer.GetLayerDefn()
    for i, row in enumerate(pts):
        feat = ogr.Feature(defn)
        for field, column in zip(fields, values):
            value = column[i]
            feat.SetField(field, None if value is None or (
                isinstance(value, float) and not np.isfinite(value)) else value.item())
        point = ogr.Geometry(ogr.wkbPoint25D)
        point.AddPoint(float(row[0]), float(row[1]), float(row[2]))
        feat.SetGeometry(point)
        layer.CreateFeature(feat)
        feat = None
    ds = None
    return out_path


def write_crown_polygons(
    polygons: Sequence[dict],
    out_path: str,
    crs_wkt: Optional[str] = None,
    attributes: Optional[Mapping[str, np.ndarray]] = None,
) -> str:
    """Записать полигоны крон в .shp.

    Args:
        polygons: геометрии в виде GeoJSON-словарей.
        out_path: путь к .shp.
        crs_wkt: СК слоя.
        attributes: атрибуты по именам полей, массивы длины len(polygons).

    Returns:
        Путь к созданному файлу.
    """
    attributes = attributes or {}
    ds, layer = _create(out_path, crs_wkt, ogr.wkbPolygon)
    fields = _add_fields(layer, attributes)
    values = [np.asarray(v) for v in attributes.values()]

    defn = layer.GetLayerDefn()
    for i, geom in enumerate(polygons):
        feat = ogr.Feature(defn)
        for field, column in zip(fields, values):
            value = column[i]
            feat.SetField(field, None if value is None or (
                isinstance(value, float) and not np.isfinite(value)) else value.item())
        feat.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(geom)))
        layer.CreateFeature(feat)
        feat = None
    ds = None
    return out_path
