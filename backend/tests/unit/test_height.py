"""Тесты height.py (извлечение отметок высот)."""

import laspy
import numpy as np
import json
from pathlib import Path

from sima_dem_core.height import extract_heights


def _make_ground_las(path: str, n: int = 100) -> str:
    """Создать LAS с ground-точками (Classification==2)."""
    las = laspy.create(point_format=3, file_version="1.2")
    las.x = np.linspace(100, 200, n, dtype=np.float64)
    las.y = np.linspace(100, 200, n, dtype=np.float64)
    las.z = np.linspace(50, 150, n, dtype=np.float64)
    las.classification = np.array([2] * n, dtype=np.uint8)
    las.write(path)
    return path


def _coords(path: str) -> np.ndarray:
    data = json.loads(Path(path).read_text())
    assert data["type"] == "FeatureCollection"
    if not data["features"]:
        return np.empty((0, 2))
    return np.array([f["geometry"]["coordinates"][:2] for f in data["features"]])


class TestHeight:

    def test_min_distance_thins_points(self, tmp_path):
        """Отметки прореживаются: соседние точки не ближе заданного расстояния."""
        inp = str(tmp_path / "test.las")
        _make_ground_las(inp, n=100)  # диагональ, шаг между точками ~1.43 м
        out = str(tmp_path / "heights.geojson")
        extract_heights(inp, min_distance_m=10.0, result_layer_name=out, crs="EPSG:32642")
        pts = _coords(out)
        assert 0 < len(pts) < 100
        d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        assert d.min() >= 10.0 - 1e-9

    def test_zero_distance_keeps_all(self, tmp_path):
        """min_distance_m=0 — прореживания нет, берутся все ground-точки."""
        inp = str(tmp_path / "test.las")
        _make_ground_las(inp, n=100)
        out = str(tmp_path / "heights.geojson")
        extract_heights(inp, min_distance_m=0, result_layer_name=out, crs="EPSG:32642")
        assert len(_coords(out)) == 100

    def test_properties_contain_alt(self, tmp_path):
        inp = str(tmp_path / "test.las")
        _make_ground_las(inp, n=100)
        out = str(tmp_path / "heights.geojson")
        extract_heights(inp, min_distance_m=10.0, result_layer_name=out, crs="EPSG:32642")
        data = json.loads(Path(out).read_text())
        assert "alt" in data["features"][0]["properties"]

    def test_empty_without_ground(self, tmp_path):
        """LAS без ground-точек → пустой GeoJSON."""
        las = laspy.create(point_format=3, file_version="1.2")
        las.x = np.array([1.0, 2.0, 3.0])
        las.y = np.array([1.0, 2.0, 3.0])
        las.z = np.array([1.0, 2.0, 3.0])
        las.classification = np.array([5, 5, 5], dtype=np.uint8)
        inp = str(tmp_path / "no_ground.las")
        las.write(inp)
        out = str(tmp_path / "empty.geojson")
        extract_heights(inp, min_distance_m=10.0, result_layer_name=out, crs="EPSG:32642")
        assert len(_coords(out)) == 0
