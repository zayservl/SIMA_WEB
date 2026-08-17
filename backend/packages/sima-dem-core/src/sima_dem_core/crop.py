"""Обрезка LAS по полигону AOI.

Порт из legacy `processings/crop_las.py`. Без PDAL — чистый laspy+shapely.
"""

from __future__ import annotations

import json

import laspy
import numpy as np
from shapely.geometry import Point, shape


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

        aoi = self._load_aoi()

        # Точки внутри полигона AOI
        points = [Point(p) for p in np.column_stack([x, y])]
        mask = np.array([aoi.contains(p) for p in points], dtype=bool)

        if np.any(mask):
            out = laspy.create(point_format=las.point_format, file_version=las.header.version)
            out.header = las.header
            out.points = las.points[mask]
            out.write(self.vls_cropped)