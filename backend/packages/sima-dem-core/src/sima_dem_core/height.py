"""Извлечение отметок высот (каждая n-я точка Ground или регулярная сетка из ЦМР).

Порт из legacy `relief_analysis/height.py`. Без QGIS — использует shapely/ogr.
Два источника (Q3/контракт heights.source):
  - 'las': каждая n-я ground-точка (Classification==2) из LAS;
  - 'dem':  регулярная сетка высот, сэмплированная из растра ЦМР.
Два формата вывода (Q3): 'geojson' (по умолчанию, обратно-совместимо) и 'shp'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import laspy
import numpy as np


def _heights_from_las(las_path: str, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    las = laspy.read(las_path)
    cls = np.asarray(las.classification)
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z = np.asarray(las.z)
    mask = cls == 2  # только ground; при отсутствии — пустой результат (как в legacy)
    x_g, y_g, z_g = x[mask], y[mask], z[mask]
    return x_g[::n], y_g[::n], z_g[::n]


def _heights_from_dem(dem_path: str, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Регулярная сетка высот из растра ЦМР: каждая n-я ячейка по строкам/столбцам."""
    import rasterio
    with rasterio.open(dem_path) as src:
        arr = src.read(1)
        nodata = src.nodata
        t = src.transform
        h, w = arr.shape
        ys, xs = np.indices((h, w))
        xs = xs[::n, ::n].ravel()
        ys = ys[::n, ::n].ravel()
        vals = arr[ys, xs]
        if nodata is not None:
            keep = vals != nodata
            xs, ys, vals = xs[keep], ys[keep], vals[keep]
        # пиксельные координаты → мировые через аффин-преобразование
        xw = t.c + xs * t.a
        yw = t.f + ys * t.e
        return xw, yw, vals


def _write_geojson(x: np.ndarray, y: np.ndarray, z: np.ndarray, out: str, crs: str) -> None:
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(px), float(py), float(pz)]},
            "properties": {"alt": float(pz)},
        }
        for px, py, pz in zip(x, y, z)
    ]
    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": features,
    }
    Path(out).write_text(json.dumps(geojson, ensure_ascii=False))


def _write_shp(x: np.ndarray, y: np.ndarray, z: np.ndarray, out: str, crs: str) -> None:
    """Записать 3D-точки высот в .shp (ESRI Shapefile) через OGR."""
    from osgeo import ogr, osr
    import os
    pts = np.column_stack([x, y, z])
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    driver = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(out):
        driver.DeleteDataSource(out)
    ds = driver.CreateDataSource(out)
    srs = None
    if crs:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(crs)
    layer_name = os.path.splitext(os.path.basename(out))[0][:10]
    layer = ds.CreateLayer(layer_name, srs=srs, geom_type=ogr.wkbPoint25D)
    layer.CreateField(ogr.FieldDefn("alt", ogr.OFTReal))
    for row in pts:
        feat = ogr.Feature(layer.GetLayerDefn())
        feat.SetField("alt", float(row[2]))
        pt = ogr.Geometry(ogr.wkbPoint25D)
        pt.AddPoint(float(row[0]), float(row[1]), float(row[2]))
        feat.SetGeometry(pt)
        layer.CreateFeature(feat)
        feat = None
    ds = None


def get_every_nth(
    las_path: str,
    n: int,
    result_layer_name: str,
    crs: str,
    out_format: str = "geojson",
    dem_path: Optional[str] = None,
) -> None:
    """Извлечь отметки высот и сохранить.

    Args:
        las_path: путь к LAS-файлу (источник 'las') либо игнорируется при source='dem'.
        n: шаг выборки.
        result_layer_name: путь выходного файла (.geojson или .shp).
        crs: CRS-строка (EPSG:XXXX или WKT).
        out_format: 'geojson' (по умолчанию) или 'shp' (требование Q3 — отметки .shp).
        dem_path: путь к растру ЦМР — если задан, источник высот 'dem' (регулярная
            сетка из растра, а не LAS). Q3 «Высота на ЦМР».
    """
    if dem_path is not None:
        x, y, z = _heights_from_dem(dem_path, n)
    else:
        x, y, z = _heights_from_las(las_path, n)
    if out_format == "shp":
        _write_shp(x, y, z, result_layer_name, crs)
    else:
        _write_geojson(x, y, z, result_layer_name, crs)