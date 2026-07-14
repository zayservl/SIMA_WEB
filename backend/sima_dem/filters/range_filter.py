"""Перцентильный фильтр.

Порт из legacy `relief_analysis/range_filter.py`. Без PDAL — чистый laspy+numpy.
"""

from __future__ import annotations

import laspy
import numpy as np


class RangeFilter:
    """Фильтр LAS: отсев точек вне перцентильного диапазона [min_pct, max_pct]."""

    def __init__(self, vls_path: str, resolution: float, min_percent: float, max_percent: float, output_file_path: str) -> None:
        self.vls_path = vls_path
        self.resolution = resolution
        self.min_percent = min_percent
        self.max_percent = max_percent
        self.output_file_path = output_file_path

    def filter(self) -> None:
        las = laspy.read(self.vls_path)
        z = np.asarray(las.z, dtype=float)
        z_min = float(np.min(z))
        z_max = float(np.max(z))
        lo = z_min + (z_max - z_min) * self.min_percent
        hi = z_min + (z_max - z_min) * self.max_percent
        mask = (z >= lo) & (z <= hi)

        out = laspy.create(point_format=las.point_format, file_version=las.header.version)
        out.header = las.header
        out.points = las.points[mask]
        out.write(self.output_file_path)