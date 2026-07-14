"""Тесты raster/smooth.py, raster/median.py, raster/tpi.py."""

import pytest
import rasterio
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter

from sima_dem.raster.smooth import gauss_smooth
from sima_dem.raster.median import med_filter
from sima_dem.raster.tpi import calculate_tpi


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


class TestGaussSmooth:

    def test_smooth_preserves_shape(self, tmp_path):
        """Гаусс-сглаживание сохраняет форму растра."""
        data = np.random.rand(20, 20).astype(np.float32) * 100
        inp = str(tmp_path / "in.tif")
        outp = str(tmp_path / "out.tif")
        _write_test_tif(inp, data)
        gauss_smooth(inp, outp, sigma=1.0, order=0, window_size=3)
        with rasterio.open(outp) as src:
            result = src.read(1)
        assert result.shape == data.shape

    def test_smooth_reduces_variance(self, tmp_path):
        """Сглаживание уменьшает дисперсию данных."""
        data = np.random.rand(30, 30).astype(np.float32) * 100
        inp = str(tmp_path / "in.tif")
        outp = str(tmp_path / "out.tif")
        _write_test_tif(inp, data)
        gauss_smooth(inp, outp, sigma=2.0, order=0, window_size=5)
        with rasterio.open(outp) as src:
            result = src.read(1)
        valid = data != -9999.0
        assert np.std(result[valid]) <= np.std(data[valid])


class TestMedFilter:

    def test_median_filter_preserves_shape(self, tmp_path):
        """Медианный фильтр сохраняет форму."""
        data = np.random.rand(15, 15).astype(np.float32) * 100
        inp = str(tmp_path / "in.tif")
        _write_test_tif(inp, data)
        med_filter(inp, window=3)
        with rasterio.open(inp) as src:
            result = src.read(1)
        assert result.shape == data.shape

    def test_median_removes_salt_noise(self, tmp_path):
        """Медианный фильтр убирает солевой шум (одиночные выбросы)."""
        data = np.full((15, 15), 10.0, dtype=np.float32)
        data[7, 7] = 1000.0  # Солевой шум
        inp = str(tmp_path / "in.tif")
        _write_test_tif(inp, data)
        med_filter(inp, window=3)
        with rasterio.open(inp) as src:
            result = src.read(1)
        assert abs(result[7, 7] - 10.0) < 50.0  # Выброс сглажен


class TestTPI:

    def test_tpi_output_exists(self, tmp_path):
        """TPI создаёт выходной растр."""
        data = np.linspace(0, 100, 30 * 30, dtype=np.float32).reshape(30, 30)
        inp = str(tmp_path / "test_dem.tif")
        _write_test_tif(inp, data, resolution=10.0)
        result = calculate_tpi(
            dem_path=inp,
            crs="EPSG:32642",
            output_folder=str(tmp_path),
            input_res=10.0,
            res=10.0,
        )
        assert Path(result).exists()

    def test_tpi_flat_surface_near_zero(self, tmp_path):
        """TPI плоской поверхности ≈ 0."""
        data = np.full((50, 50), 100.0, dtype=np.float32)
        inp = str(tmp_path / "flat_dem.tif")
        _write_test_tif(inp, data, resolution=10.0)
        result = calculate_tpi(
            dem_path=inp,
            crs="EPSG:32642",
            output_folder=str(tmp_path),
            input_res=10.0,
            res=10.0,
        )
        with rasterio.open(result) as src:
            tpi = src.read(1)
        valid = tpi != -9999.0
        if np.any(valid):
            assert np.max(np.abs(tpi[valid])) < 1.0