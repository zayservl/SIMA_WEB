"""Извлечение отметок высот (каждая n-я точка Ground).

Порт из legacy `relief_analysis/height.py`. Без QGIS — использует shapely.
"""

from __future__ import annotations

import laspy
import numpy as np
from shapely.geometry import Point
import json
from pathlib import Path


def get_every_nth(las_path: str, n: int, result_layer_name: str, crs: str) -> None:
    """Извлечь каждую n-ю ground-точку и сохранить как GeoJSON.

    Args:
        las_path: путь к LAS-файлу
        n: шаг выборки (каждая n-я точка)
        result_layer_name: путь выходного GeoJSON
        crs: CRS-строка (EPSG:XXXX или WKT)
    """
    las = laspy.read(las_path)
    x = np.asarray(las.x)
    y = np.asarray(las.y)
    z = np.asarray(las.z)
    cls = np.asarray(las.classification)

    ground_mask = cls == 2
    x_g = x[ground_mask]
    y_g = y[ground_mask]
    z_g = z[ground_mask]

    x_n = x_g[::n]
    y_n = y_g[::n]
    z_n = z_g[::n]

    features = []
    for px, py, pz in zip(x_n, y_n, z_n):
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(px), float(py), float(pz)]},
            "properties": {"alt": float(pz)},
        })

    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": features,
    }
    Path(result_layer_name).write_text(json.dumps(geojson, ensure_ascii=False))