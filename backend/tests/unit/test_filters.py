"""Тесты filters/manual_filter.py, stat_filter.py, range_filter.py."""

import pytest
import laspy
import numpy as np
from pathlib import Path

from sima_dem.filters.manual_filter import ManualFilter
from sima_dem.filters.stat_filter import StatFilter
from sima_dem.filters.range_filter import RangeFilter


def _make_las(path: str, z_values: list[float], classifications: list[int] = None) -> str:
    """Создать минимальный LAS с заданными Z."""
    las = laspy.create(point_format=3, file_version="1.2")
    n = len(z_values)
    las.x = np.linspace(0, 10, n, dtype=np.float64)
    las.y = np.linspace(0, 10, n, dtype=np.float64)
    las.z = np.array(z_values, dtype=np.float64)
    if classifications is None:
        classifications = [2] * n
    las.classification = np.array(classifications, dtype=np.uint8)
    las.write(path)
    return path


class TestManualFilter:

    def test_basic_filter(self, tmp_path):
        """Фильтр отсекает точки вне [z_min, z_max]."""
        inp = str(tmp_path / "in.las")
        outp = str(tmp_path / "out.las")
        _make_las(inp, [1.0, 5.0, 10.0, 15.0, 20.0])
        f = ManualFilter(inp, resolution=1.0, z_min=5.0, z_max=15.0, output_file_path=outp)
        f.filter()
        result = laspy.read(outp)
        z = np.asarray(result.z)
        assert len(z) == 3  # 5.0, 10.0, 15.0
        assert np.all((z >= 5.0) & (z <= 15.0))

    def test_no_points_in_range(self, tmp_path):
        """Все точки вне диапазона → пустой результат."""
        inp = str(tmp_path / "in.las")
        outp = str(tmp_path / "out.las")
        _make_las(inp, [100.0, 200.0, 300.0])
        f = ManualFilter(inp, resolution=1.0, z_min=0.0, z_max=50.0, output_file_path=outp)
        f.filter()
        result = laspy.read(outp)
        assert len(result.points) == 0


class TestStatFilter:

    def test_basic_stat_filter(self, tmp_path):
        """Статистический фильтр оставляет точки в m*sigma от среднего."""
        inp = str(tmp_path / "in.las")
        outp = str(tmp_path / "out.las")
        # Среднее = 10, sigma ≈ 6.45
        z = [0.0, 5.0, 10.0, 15.0, 20.0]
        _make_las(inp, z)
        f = StatFilter(inp, resolution=1.0, m=1.0, output_file_path=outp)
        f.filter()
        result = laspy.read(outp)
        z_out = np.asarray(result.z, dtype=float)
        mu = np.mean(z)
        sigma = np.std(z)
        lo = mu - 1.0 * sigma
        hi = mu + 1.0 * sigma
        assert len(z_out) == sum(1 for v in z if lo <= v <= hi)

    def test_large_m_keeps_all(self, tmp_path):
        """При большом m остаются все точки."""
        inp = str(tmp_path / "in.las")
        outp = str(tmp_path / "out.las")
        _make_las(inp, [1.0, 5.0, 10.0])
        f = StatFilter(inp, resolution=1.0, m=100.0, output_file_path=outp)
        f.filter()
        result = laspy.read(outp)
        assert len(result.points) == 3


class TestRangeFilter:

    def test_basic_range_filter(self, tmp_path):
        """Перцентильный фильтр оставляет точки в [min_pct, max_pct] диапазона."""
        inp = str(tmp_path / "in.las")
        outp = str(tmp_path / "out.las")
        _make_las(inp, [0.0, 25.0, 50.0, 75.0, 100.0])
        f = RangeFilter(inp, resolution=1.0, min_percent=0.25, max_percent=0.75, output_file_path=outp)
        f.filter()
        result = laspy.read(outp)
        z_out = np.asarray(result.z, dtype=float)
        assert len(z_out) == 3  # 25, 50, 75
        assert np.all(z_out >= 25.0)