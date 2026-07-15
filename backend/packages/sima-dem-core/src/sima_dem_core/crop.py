"""Обрезка LAS по полигону AOI.

Порт из legacy `processings/crop_las.py`. Без PDAL — чистый laspy+shapely.
"""

from __future__ import annotations

import laspy
import numpy as np
from shapely.geometry import Point, shape
import json


class Crop:
    """Обрезка LAS-точек по полигону AOI (GeoJSON или shapefile)."""

    def __init__(self, vls_cropped: str, vls_path: str, shapefile: str) -> None:
        self.vls_path = vls_path
        self.vls_cropped = vls_cropped
        self.shapefile = shapefile

    def _load_aoi(self) -> shape:
        """Загрузить AOI-полигон из GeoJSON shapefile."""
        with open(self.shapefile, "r") as f:
            data = json.load(f)
        if data["type"] == "FeatureCollection":
            geom = data["features"][0]["geometry"]
        else:
            geom = data
        return shape(geom)

    def cropCalc(self) -> None:
        """Прочитать LAS, отфильтровать точки внутри AOI, записать результат."""
        las = laspy.read(self.vls_path)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z)
        intensity = np.asarray(las.intensity)
        r = np.asarray(las.red) if hasattr(las, "red") else np.zeros(len(x), dtype=np.uint16)
        g = np.asarray(las.green) if hasattr(las, "green") else np.zeros(len(x), dtype=np.uint16)
        b = np.asarray(las.blue) if hasattr(las, "blue") else np.zeros(len(x), dtype=np.uint16)
        cls = np.asarray(las.classification)

        aoi = self._load_aoi()

        # Векторизованная проверка: точки внутри полигона
        pts = np.column_stack([x, y])
        from shapely import STRtree
        from shapely.geometry import Point
        points = [Point(p) for p in pts]
        tree = STRtree(points)
        # Простая проверка: для каждой точки — inside polygon
        mask = np.array([aoi.contains(p) for p in points], dtype=bool)

        if np.any(mask):
            out = laspy.create(point_format=las.point_format, file_version=las.header.version)
            out.header = las.header
            out.points = las.points[mask]
            out.write(self.vls_cropped)