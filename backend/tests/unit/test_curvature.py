"""Тесты curvature.py (slope, aspect)."""

import pytest
import rasterio
import numpy as np
from pathlib import Path

from sima_dem.curvature import CurvatureProcessing


def _write_test_tif(path: str, data: np.ndarray, nodata: float = -9999.0, resolution: float = 1.0) -> str:
    """Записать тестовый GeoTIFF."""
    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "nodata": nodata,
        "width": data.shape[1],
        "height": data.shape[0],
        "count": 1,
        "crs": "EPSG:32642",
        "transform": rasterio.transform.from_origin(0, data.shape[0] * resolution, resolution, resolution),
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype(np.float32), 1)
    return path


class TestCurvatureProcessing:

    def test_calculate_slope(self, tmp_path):
        """Расчёт уклона создаёт выходной растр."""
        data = np.linspace(0, 100, 20 * 20, dtype=np.float32).reshape(20, 20)
        inp = str(tmp_path / "test_dem.tif")
        _write_test_tif(inp, data, resolution=10.0)
        cp = CurvatureProcessing()
        slope = cp.calculate_slope(inp, "EPSG:32642", 10.0, 10.0, str(tmp_path))
        assert Path(slope).exists()
        assert len(cp.slopes) == 1

    def test_calculate_aspect(self, tmp_path):
        """Расчёт экспозиции создаёт выходной растр."""
        data = np.linspace(0, 100, 20 * 20, dtype=np.float32).reshape(20, 20)
        inp = str(tmp_path / "test_dem.tif")
        _write_test_tif(inp, data, resolution=10.0)
        cp = CurvatureProcessing()
        aspect = cp.calculate_aspect(inp, "EPSG:32642", 10.0, 10.0, str(tmp_path))
        assert Path(aspect).exists()
        assert len(cp.aspects) == 1

    def test_slope_flat_is_zero(self, tmp_path):
        """Уклон плоской поверхности ≈ 0."""
        data = np.full((20, 20), 100.0, dtype=np.float32)
        inp = str(tmp_path / "flat_dem.tif")
        _write_test_tif(inp, data, resolution=10.0)
        cp = CurvatureProcessing()
        slope = cp.calculate_slope(inp, "EPSG:32642", 10.0, 10.0, str(tmp_path))
        with rasterio.open(slope) as src:
            sl = src.read(1)
        valid = sl != -9999.0
        if np.any(valid):
            assert np.max(np.abs(sl[valid])) < 5.0  # Near-zero slope