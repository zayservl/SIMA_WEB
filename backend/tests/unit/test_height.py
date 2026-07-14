"""Тесты height.py (извлечение отметок высот)."""

import pytest
import laspy
import numpy as np
import json
from pathlib import Path

from sima_dem.height import get_every_nth


def _make_ground_las(path: str, n: int = 100) -> str:
    """Создать LAS с ground-точками (Classification==2)."""
    las = laspy.create(point_format=3, file_version="1.2")
    las.x = np.linspace(100, 200, n, dtype=np.float64)
    las.y = np.linspace(100, 200, n, dtype=np.float64)
    las.z = np.linspace(50, 150, n, dtype=np.float64)
    las.classification = np.array([2] * n, dtype=np.uint8)
    las.write(path)
    return path


class TestHeight:

    def test_get_every_nth(self, tmp_path):
        """Извлечение каждой n-й ground-точки."""
        inp = str(tmp_path / "test.las")
        _make_ground_las(inp, n=100)
        out = str(tmp_path / "heights.geojson")
        get_every_nth(inp, n=10, result_layer_name=out, crs="EPSG:32642")
        data = json.loads(Path(out).read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 10  # 100 ground points / 10 = 10
        assert "alt" in data["features"][0]["properties"]

    def test_get_every_nth_empty(self, tmp_path):
        """LAS без ground-точек → пустой GeoJSON."""
        las = laspy.create(point_format=3, file_version="1.2")
        las.x = np.array([1.0, 2.0, 3.0])
        las.y = np.array([1.0, 2.0, 3.0])
        las.z = np.array([1.0, 2.0, 3.0])
        las.classification = np.array([5, 5, 5], dtype=np.uint8)
        inp = str(tmp_path / "no_ground.las")
        las.write(inp)
        out = str(tmp_path / "empty.geojson")
        get_every_nth(inp, n=10, result_layer_name=out, crs="EPSG:32642")
        data = json.loads(Path(out).read_text())
        assert len(data["features"]) == 0