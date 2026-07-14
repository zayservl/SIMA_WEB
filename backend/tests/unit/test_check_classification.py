"""Тесты check_classification.py."""

import pytest
import laspy
import numpy as np
import tempfile
from pathlib import Path

from sima_dem.check_classification import CheckClassification


def _make_las(path: str, classifications: list[int]) -> str:
    """Создать минимальный LAS с заданными классификациями."""
    las = laspy.create(point_format=3, file_version="1.2")
    n = len(classifications)
    las.x = np.linspace(0, 10, n, dtype=np.float64)
    las.y = np.linspace(0, 10, n, dtype=np.float64)
    las.z = np.linspace(0, 5, n, dtype=np.float64)
    las.classification = np.array(classifications, dtype=np.uint8)
    las.write(path)
    return path


class TestCheckClassification:

    def test_ground_present(self, tmp_path):
        """LAS с Classification==2 → is_ground=True."""
        path = str(tmp_path / "ground.las")
        _make_las(path, [2, 2, 2, 3, 4, 5])
        cc = CheckClassification(path)
        assert cc.is_ground is True
        assert cc.xmin == 0.0
        assert cc.xmax == pytest.approx(10.0)

    def test_ground_absent(self, tmp_path):
        """LAS без Classification==2 → is_ground=False."""
        path = str(tmp_path / "noground.las")
        _make_las(path, [1, 3, 4, 5])
        cc = CheckClassification(path)
        assert cc.is_ground is False

    def test_empty_las(self, tmp_path):
        """Пустой LAS → is_ground=False."""
        path = str(tmp_path / "empty.las")
        las = laspy.create(point_format=3, file_version="1.2")
        las.x = np.array([], dtype=np.float64)
        las.y = np.array([], dtype=np.float64)
        las.z = np.array([], dtype=np.float64)
        las.classification = np.array([], dtype=np.uint8)
        las.write(path)
        cc = CheckClassification(path)
        assert cc.is_ground is False

    def test_invalid_path(self):
        """Несуществующий файл → is_ground=False, без исключения."""
        cc = CheckClassification("/nonexistent/path/file.las")
        assert cc.is_ground is False