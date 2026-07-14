"""Проверка наличия класса Ground в LAS-файле.

Порт из legacy `processings/check_classification.py`.
Чистый Python: laspy + numpy.
"""

from __future__ import annotations

import numpy as np
import laspy


class CheckClassification:
    """Прочитать LAS, проверить, содержит ли он Classification==2 (ground)."""

    def __init__(self, input_path: str) -> None:
        self.input_path = input_path
        self.xmax: float = 0.0
        self.xmin: float = 0.0
        self.ymax: float = 0.0
        self.ymin: float = 0.0
        self.is_ground: bool = False
        self._read()

    def _read(self) -> None:
        try:
            las = laspy.read(self.input_path)
        except Exception:  # noqa: BLE001
            self.is_ground = False
            return
        cls = np.asarray(las.classification)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        if len(x) > 0:
            self.xmax = float(np.max(x))
            self.xmin = float(np.min(x))
            self.ymax = float(np.max(y))
            self.ymin = float(np.min(y))
        self.is_ground = bool(np.any(cls == 2))