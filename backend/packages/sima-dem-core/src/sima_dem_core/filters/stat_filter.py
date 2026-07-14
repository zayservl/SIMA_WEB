"""Статистический (m·σ) фильтр.

Порт из legacy `relief_analysis/stat_filter.py`. Без PDAL — чистый laspy+numpy.
"""

from __future__ import annotations

import laspy
import numpy as np


class StatFilter:
    """Фильтр LAS: отсев точек вне диапазона [mu - m*sigma, mu + m*sigma]."""

    def __init__(self, vls_path: str, resolution: float, m: float, output_file_path: str) -> None:
        self.vls_path = vls_path
        self.resolution = resolution
        self.m = m
        self.output_file_path = output_file_path

    def filter(self) -> None:
        las = laspy.read(self.vls_path)
        z = np.asarray(las.z, dtype=float)
        mu = float(np.mean(z))
        sigma = float(np.std(z))
        mask = (z >= mu - self.m * sigma) & (z <= mu + self.m * sigma)

        out = laspy.create(point_format=las.point_format, file_version=las.header.version)
        out.header = las.header
        out.points = las.points[mask]
        out.write(self.output_file_path)