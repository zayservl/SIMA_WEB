"""Статистическое удаление выбросов (outlier removal).

Порт из legacy `relief_analysis/k_means_filter.py`. Использует PDAL filters.outlier.
"""

from __future__ import annotations

import json
import pdal


class OutlierFilter:
    """Удаление выбросов через PDAL filters.outlier (statistical method)."""

    def __init__(self, vls_path: str, resolution: float, neighbours: int, m: float, output_file_path: str) -> None:
        self.vls_path = vls_path
        self.resolution = resolution
        self.neighbours = neighbours
        self.m = m
        self.output_file_path = output_file_path

    def filter(self) -> None:
        pipeline = [
            self.vls_path,
            {
                "type": "filters.outlier",
                "method": "statistical",
                "class": 66,
                "mean_k": self.neighbours,
                "multiplier": self.m,
            },
            {
                "type": "filters.range",
                "limits": "Classification![66:66]",
            },
            self.output_file_path,
        ]
        pipe = pdal.Pipeline(json.dumps(pipeline))
        pipe.execute()