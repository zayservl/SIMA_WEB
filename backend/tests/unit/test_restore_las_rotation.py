"""Регрессионный тест: restore_absolute_las не должен поворачивать растр на 90°.

Баг: rasterio `~transform * (x, y)` возвращает (col, row), а НЕ (row, col).
restore_las.py присваивал результат как (rows, cols) — транспонированная индексация
давала поворот на 90° на неквадратных растрах. На квадратных (demo_data 7143x7143)
баг был невидим.
"""

import numpy as np
import rasterio
import laspy
import pytest
from pathlib import Path
from rasterio.transform import from_origin

from tests.fixtures.restore_las import restore_absolute_las


def _make_non_square_dsm(path: str, height: int = 10, width: int = 5) -> None:
    """Создать неквадратный DSM с уникальным значением в каждом пикселе.

    Значение пикселя = row * 1000 + col — гарантирует, что (row, col) и (col, row)
    дают разные значения (кроме (0,0)).
    """
    arr = np.array([[r * 1000 + c for c in range(width)] for r in range(height)], dtype=np.float32)
    transform = from_origin(0, height, 1, 1)
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width,
                       count=1, dtype="float32", crs="EPSG:32637",
                       transform=transform, nodata=-9999) as dst:
        dst.write(arr, 1)


def _make_ground_las(path: str, dsm_path: str, n_points: int = 20) -> None:
    """Создать LAS с ground-точками в центрах пикселей неквадратного DSM."""
    with rasterio.open(dsm_path) as src:
        transform = src.transform
        H, W = src.height, src.width

    las = laspy.create(point_format=3, file_version="1.2")
    xs, ys, zs = [], [], []
    for r in range(H):
        for c in range(W):
            x, y = rasterio.transform.xy(transform, r, c, offset="center")
            xs.append(x)
            ys.append(y)
            zs.append(0.0)
    las.x = np.array(xs, dtype=np.float64)
    las.y = np.array(ys, dtype=np.float64)
    las.z = np.array(zs, dtype=np.float64)
    las.classification = np.array([2] * len(xs), dtype=np.uint8)
    las.write(path)


class TestRestoreLasNoRotation:

    def test_non_square_raster_no_90_rotation(self, tmp_path: Path):
        """На неквадратном DSM (10x5) restored LAS берёт Z из правильного пикселя."""
        height, width = 10, 5
        dsm_path = str(tmp_path / "test_dsm.tif")
        _make_non_square_dsm(dsm_path, height=height, width=width)

        tlo_path = str(tmp_path / "test_tlo.las")
        _make_ground_las(tlo_path, dsm_path)

        out_las = str(tmp_path / "restored.las")
        restore_absolute_las(tlo_path, dsm_path, out_las)

        restored = laspy.read(out_las)
        with rasterio.open(dsm_path) as src:
            dsm = src.read(1)
            transform = src.transform

        x = np.asarray(restored.x)
        y = np.asarray(restored.y)
        z = np.asarray(restored.z)
        inv = ~transform
        cols, rows = inv * (x, y)
        rows = rows.astype(int)
        cols = cols.astype(int)

        expected_z = dsm[rows, cols]
        assert np.allclose(z, expected_z, atol=0.01), (
            f"Z mismatch — possible 90° rotation. "
            f"Expected dsm[rows, cols], got transposed values.\n"
            f"First 5 expected: {expected_z[:5]}\n"
            f"First 5 actual:   {z[:5]}"
        )

    def test_square_raster_still_correct(self, tmp_path: Path):
        """На квадратном DSM (5x5) restored LAS тоже берёт правильный пиксель."""
        dsm_path = str(tmp_path / "square_dsm.tif")
        _make_non_square_dsm(dsm_path, height=5, width=5)

        tlo_path = str(tmp_path / "square_tlo.las")
        _make_ground_las(tlo_path, dsm_path)

        out_las = str(tmp_path / "restored.las")
        restore_absolute_las(tlo_path, dsm_path, out_las)

        restored = laspy.read(out_las)
        with rasterio.open(dsm_path) as src:
            dsm = src.read(1)
            transform = src.transform

        x = np.asarray(restored.x)
        y = np.asarray(restored.y)
        z = np.asarray(restored.z)
        inv = ~transform
        cols, rows = inv * (x, y)
        rows = rows.astype(int)
        cols = cols.astype(int)

        expected_z = dsm[rows, cols]
        assert np.allclose(z, expected_z, atol=0.01)