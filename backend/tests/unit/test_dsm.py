"""Тесты dsm.py (построение DSM из LAS)."""

import pytest
import laspy
import numpy as np
import rasterio
from pathlib import Path

from sima_dem_dsm.dsm import DSMBuilder, DSMConfig


def _make_surface_las(path: str, n: int = 500) -> str:
    las = laspy.create(point_format=3, file_version="1.2")
    xs = np.linspace(100, 200, n, dtype=np.float64)
    ys = np.linspace(100, 200, n, dtype=np.float64)
    zs = np.linspace(90, 110, n, dtype=np.float64)
    las.x = xs
    las.y = ys
    las.z = zs
    las.classification = np.array([2] * n, dtype=np.uint8)
    las.write(path)
    return path


class TestDSMBuilder:

    def test_build_creates_raster(self, tmp_path):
        las_dir = tmp_path / "las"
        las_dir.mkdir()
        las_path = str(las_dir / "test.las")
        _make_surface_las(las_path, n=200)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        builder = DSMBuilder(
            output=str(out_dir),
            crs="EPSG:32642",
            config=DSMConfig(resolution=1.0, interpolate=False),
        )
        result = builder.build(las_path)
        assert Path(result).exists()
        assert result in builder.raster

    def test_build_with_interpolation(self, tmp_path):
        las_dir = tmp_path / "las"
        las_dir.mkdir()
        las_path = str(las_dir / "test.las")
        _make_surface_las(las_path, n=300)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        builder = DSMBuilder(
            output=str(out_dir),
            crs="EPSG:32642",
            config=DSMConfig(resolution=1.0, interpolate=True, max_search_distance=50),
        )
        result = builder.build(las_path)
        assert Path(result).exists()

    def test_build_custom_output_path(self, tmp_path):
        las_dir = tmp_path / "las"
        las_dir.mkdir()
        las_path = str(las_dir / "test.las")
        _make_surface_las(las_path, n=200)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        custom_path = str(out_dir / "custom_dsm.tif")
        builder = DSMBuilder(
            output=str(out_dir),
            crs="EPSG:32642",
            config=DSMConfig(resolution=1.0, interpolate=False),
        )
        result = builder.build(las_path, out_path=custom_path)
        assert result == custom_path
        assert Path(result).exists()