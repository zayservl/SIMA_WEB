"""Пороговая фильтрация по Z[z_min:z_max].

Порт из legacy `relief_analysis/manual_filt.py`. Без PDAL — чистый laspy.
"""

from __future__ import annotations

import laspy
import numpy as np


class ManualFilter:
    """Фильтр LAS по диапазону Z (min, max)."""

    def __init__(self, vls_path: str, resolution: float, z_min: float, z_max: float, output_file_path: str) -> None:
        self.vls_path = vls_path
        self.resolution = resolution
        self.z_min = z_min
        self.z_max = z_max
        self.output_file_path = output_file_path

    def filter(self) -> None:
        """Прочитать LAS, отфильтровать по Z, записать результат."""
        las = laspy.read(self.vls_path)
        z = np.asarray(las.z)
        mask = (z >= self.z_min) & (z <= self.z_max)

        out = laspy.create(point_format=las.point_format, file_version=las.header.version)
        out.header = las.header
        out.points = las.points[mask]
        out.write(self.output_file_path)