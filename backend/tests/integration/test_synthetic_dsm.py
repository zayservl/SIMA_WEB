"""Non-circular synthetic DSM convergence test.

Creates a known LAS with absolute Z (NOT derived from reference),
builds DSM, verifies the output matches the known surface within 5%.
This is the non-tautological validation that Oracle requested.
"""

import pytest
import numpy as np
import laspy
import rasterio
from pathlib import Path

from sima_dem.dsm import DSMBuilder
from sima_dem.ground import GroundProcessing

# CRS for synthetic test
SYNTH_CRS = "EPSG:32642"


def _make_synthetic_ground_las(path: str, grid_size: int = 50, resolution: float = 1.0) -> str:
    """Create a synthetic LAS with known absolute ground heights.

    The surface is a known paraboloid: Z = 100 + 0.001 * (x^2 + y^2).
    This is NOT derived from any reference — the ground truth is analytical.
    """
    las = laspy.create(point_format=3, file_version="1.2")
    xs = np.repeat(np.arange(0, grid_size, resolution, dtype=np.float64), grid_size)
    ys = np.tile(np.arange(0, grid_size, resolution, dtype=np.float64), grid_size)
    # Paraboloid surface: known, deterministic, non-circular
    zs = 100.0 + 0.001 * (xs ** 2 + ys ** 2)
    las.x = xs + 500000.0  # Offset to valid UTM coordinates
    las.y = ys + 6000000.0
    las.z = zs
    las.classification = np.array([2] * len(xs), dtype=np.uint8)  # Ground
    las.write(path)
    return path


def _expected_surface(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The analytical ground-truth surface: Z = 100 + 0.001 * (x^2 + y^2)."""
    return 100.0 + 0.001 * (x ** 2 + y ** 2)


class TestSyntheticDSMConvergence:
    """Non-circular DSM convergence test with analytical ground truth."""

    def test_dtm_from_known_surface_converges(self, tmp_path):
        """Build DTM from synthetic LAS with known paraboloid surface.

        The DTM should converge to the analytical surface within 5% RMSE/mean.
        This is NOT circular: the input LAS has known Z values that are
        independent of any reference raster.
        """
        # Create synthetic LAS with known surface
        las_path = str(tmp_path / "synthetic_ground.las")
        grid_size = 50
        _make_synthetic_ground_las(las_path, grid_size=grid_size, resolution=1.0)

        # Build DTM (ЦМР) from ground points
        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        gp = GroundProcessing(
            output=out_dir,
            resolution=1.0,
            crs=SYNTH_CRS,
            save_ground_las=False,
            interpolate=True,
            interpol_dist=10,
        )
        gp.get_raster(las_path)
        dtm_path = gp.raster[0]

        # Read the computed DTM
        with rasterio.open(dtm_path) as src:
            dtm = src.read(1).astype(float)
            dtm_transform = src.transform
            dtm_nodata = src.nodata

        # Build expected surface at each pixel center
        height, width = dtm.shape
        expected = np.zeros((height, width), dtype=float)
        for r in range(height):
            for c in range(width):
                x, y = dtm_transform * (c + 0.5, r + 0.5)
                expected[r, c] = _expected_surface(x - 500000.0, y - 6000000.0)

        # Compare
        if dtm_nodata is not None:
            valid = dtm != dtm_nodata
        else:
            valid = np.ones_like(dtm, dtype=bool)

        diff = np.abs(dtm[valid] - expected[valid])
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        mean_val = float(np.mean(expected[valid]))
        relative_error = rmse / mean_val if mean_val != 0 else float("inf")

        print(f"Synthetic DTM: RMSE={rmse:.6f}, Mean={mean_val:.4f}, RelError={relative_error:.6%}")
        assert relative_error < 0.05, (
            f"Synthetic DTM convergence failed: relative error {relative_error:.6%} >= 5%"
        )

    def test_dtm_shape_matches_input_extent(self, tmp_path):
        """DTM raster dimensions are reasonable for the input extent."""
        las_path = str(tmp_path / "synthetic_ground.las")
        _make_synthetic_ground_las(las_path, grid_size=30, resolution=1.0)

        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        gp = GroundProcessing(
            output=out_dir,
            resolution=1.0,
            crs=SYNTH_CRS,
            save_ground_las=False,
        )
        gp.get_raster(las_path)
        dtm_path = gp.raster[0]

        with rasterio.open(dtm_path) as src:
            dtm = src.read(1)
        # Input was 30x30 grid at 1m resolution
        assert dtm.shape[0] >= 20, f"DTM too small: {dtm.shape}"
        assert dtm.shape[1] >= 20, f"DTM too small: {dtm.shape}"

    def test_dtm_z_range_within_expected_bounds(self, tmp_path):
        """DTM Z values are within the expected range of the paraboloid."""
        las_path = str(tmp_path / "synthetic_ground.las")
        _make_synthetic_ground_las(las_path, grid_size=50, resolution=1.0)

        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()
        gp = GroundProcessing(
            output=out_dir,
            resolution=1.0,
            crs=SYNTH_CRS,
            save_ground_las=False,
            interpolate=True,
            interpol_dist=10,
        )
        gp.get_raster(las_path)
        dtm_path = gp.raster[0]

        with rasterio.open(dtm_path) as src:
            dtm = src.read(1).astype(float)
            nodata = src.nodata

        if nodata is not None:
            valid = dtm[dtm != nodata]
        else:
            valid = dtm.flatten()

        # Paraboloid: Z = 100 + 0.001*(x^2+y^2), max at corner: 100 + 0.001*(49^2+49^2) ≈ 104.8
        assert np.min(valid) >= 95.0, f"DTM min too low: {np.min(valid)}"
        assert np.max(valid) <= 110.0, f"DTM max too high: {np.max(valid)}"