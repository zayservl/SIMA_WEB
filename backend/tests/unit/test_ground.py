"""Тесты ground.py (ЦМР — GroundProcessing)."""

import pytest
import laspy
import numpy as np
import rasterio
from pathlib import Path

from sima_dem.ground import GroundProcessing


def _make_ground_las(path: str, n: int = 500) -> str:
    """Создать тестовый LAS с ground-точками (Classification==2)."""
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


def _make_unclassified_las(path: str, n: int = 500) -> str:
    """Создать тестовый LAS без ground-классификации (Classification==0)."""
    las = laspy.create(point_format=3, file_version="1.2")
    xs = np.linspace(100, 200, n, dtype=np.float64)
    ys = np.linspace(100, 200, n, dtype=np.float64)
    zs = np.linspace(90, 110, n, dtype=np.float64)
    las.x = xs
    las.y = ys
    las.z = zs
    las.classification = np.array([0] * n, dtype=np.uint8)
    las.write(path)
    return path


class TestGroundProcessing:

    def test_get_raster_from_ground(self, tmp_path):
        """Построение ЦМР из уже классифицированного LAS (ground)."""
        las_path = str(tmp_path / "ground.las")
        _make_ground_las(las_path, n=200)
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        gp = GroundProcessing(
            output=out_dir,
            resolution=1.0,
            crs="EPSG:32642",
            save_ground_las=False,
        )
        gp.get_raster(las_path)
        assert len(gp.raster) == 1
        assert Path(gp.raster[0]).exists()

    def test_get_raster_from_unclassified(self, tmp_path):
        """Построение ЦМР из неклассифицированного LAS (SMRF)."""
        las_path = str(tmp_path / "raw.las")
        _make_unclassified_las(las_path, n=200)
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        gp = GroundProcessing(
            output=out_dir,
            resolution=1.0,
            crs="EPSG:32642",
            save_ground_las=False,
        )
        gp.get_raster(las_path)
        assert len(gp.raster) == 1
        assert Path(gp.raster[0]).exists()

    def test_get_raster_name(self, tmp_path):
        """Корректное имя выходного растра."""
        gp = GroundProcessing(
            output=str(tmp_path),
            resolution=1.0,
            crs="EPSG:32642",
        )
        raster, smoothed = gp._get_raster_name("/tmp/test_relief.las", None)
        assert "test_dem.tif" in raster
        assert "test_dem_smooth.tif" in smoothed

    def test_interpolate_fills_nodata(self, tmp_path):
        """Интерполяция заполняет nodata-пиксели."""
        # Создать тестовый GeoTIFF с nodata
        data = np.full((20, 20), 100.0, dtype=np.float32)
        data[5:10, 5:10] = -9999.0  # nodata holes
        profile = {
            "driver": "GTiff",
            "dtype": "float32",
            "nodata": -9999.0,
            "width": 20,
            "height": 20,
            "count": 1,
            "crs": "EPSG:32642",
            "transform": rasterio.transform.from_origin(0, 20, 1, 1),
        }
        tif_path = str(tmp_path / "test_dem.tif")
        with rasterio.open(tif_path, "w", **profile) as dst:
            dst.write(data, 1)
        gp = GroundProcessing(
            output=str(tmp_path),
            resolution=1.0,
            crs="EPSG:32642",
            interpolate=True,
            interpol_dist=100,
        )
        gp._interpolate(tif_path)
        with rasterio.open(tif_path) as src:
            result = src.read(1)
        # Проверим, что nodata уменьшилось
        nodata_count = np.sum(result == -9999.0)
        assert nodata_count < 25  # Исходно было 25 nodata пикселей