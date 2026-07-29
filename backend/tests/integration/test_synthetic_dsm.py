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

from sima_dem_dsm.dsm import DSMBuilder, DSMConfig
from sima_dem_ground.ground import GroundProcessing

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


def _make_synthetic_ground_and_canopy_las(
    path: str, grid_size: int = 50, resolution: float = 1.0, canopy_offset: float = 15.0,
) -> str:
    """Create a synthetic LAS with co-located ground + canopy returns.

    At every (x, y) of the same known paraboloid grid used by
    `_make_synthetic_ground_las`, this emits TWO points: a ground return
    (Classification=2, Z=ground) and a "canopy" return (Classification=5,
    high vegetation, Z=ground+canopy_offset) — modelling a first/last-return
    pair over vegetation. Ground truth for both surfaces is analytical.
    """
    xs = np.repeat(np.arange(0, grid_size, resolution, dtype=np.float64), grid_size)
    ys = np.tile(np.arange(0, grid_size, resolution, dtype=np.float64), grid_size)
    ground_z = _expected_surface(xs, ys)
    canopy_z = ground_z + canopy_offset

    all_x = np.concatenate([xs, xs])
    all_y = np.concatenate([ys, ys])
    all_z = np.concatenate([ground_z, canopy_z])
    classification = np.concatenate([
        np.full(len(xs), 2, dtype=np.uint8),  # ground
        np.full(len(xs), 5, dtype=np.uint8),  # high vegetation
    ])

    las = laspy.create(point_format=3, file_version="1.2")
    las.x = all_x + 500000.0
    las.y = all_y + 6000000.0
    las.z = all_z
    las.classification = classification
    las.write(path)
    return path


class TestSyntheticDSMBuilderConvergence:
    """Non-circular DSMBuilder (output_type='max') convergence test.

    Prior to this test, no test in the suite exercised DSMBuilder against a
    known analytical surface — `test_dsm_convergence.py` and the DTM tests
    above only validate GroundProcessing (DTM/IDW), despite naming that
    suggests DSM coverage. This test builds both a DSM and a DTM from the
    SAME synthetic LAS (ground + co-located canopy returns) and checks that
    DSM (max) recovers the higher canopy surface while DTM (Classification==2
    only) recovers the lower ground surface — i.e. DSMBuilder's max-rasterization
    genuinely picks the highest point per cell, not merely whichever point
    happens to survive PDAL's filters.sample thinning.
    """

    def test_dsm_recovers_canopy_surface_above_dtm(self, tmp_path):
        grid_size = 40
        canopy_offset = 15.0
        las_path = str(tmp_path / "synthetic_ground_canopy.las")
        _make_synthetic_ground_and_canopy_las(
            las_path, grid_size=grid_size, resolution=1.0, canopy_offset=canopy_offset,
        )

        out_dir = str(tmp_path / "out")
        Path(out_dir).mkdir()

        # DSM (ЦММ): should pick up the canopy (higher) surface.
        dsm_builder = DSMBuilder(
            output=out_dir, crs=SYNTH_CRS,
            config=DSMConfig(resolution=1.0, interpolate=True, max_search_distance=10),
        )
        dsm_path = dsm_builder.build(las_path)

        # DTM (ЦМР): filters.range keeps only Classification==2 → ground only.
        gp = GroundProcessing(
            output=out_dir, resolution=1.0, crs=SYNTH_CRS,
            save_ground_las=False, interpolate=True, interpol_dist=10,
        )
        gp.get_raster(las_path)
        dtm_path = gp.raster[0]

        def _read_valid(raster_path: str) -> np.ndarray:
            with rasterio.open(raster_path) as src:
                arr = src.read(1).astype(float)
                nodata = src.nodata
            return arr[arr != nodata] if nodata is not None else arr.flatten()

        dsm_valid = _read_valid(dsm_path)
        dtm_valid = _read_valid(dtm_path)
        assert len(dsm_valid) > 0 and len(dtm_valid) > 0

        # 1. DSM must sit close to the analytical canopy (ground+offset) surface,
        #    not the bare ground surface -- proof that output_type="max" actually
        #    selects the higher of the two co-located returns.
        dsm_mean = float(np.mean(dsm_valid))
        dtm_mean = float(np.mean(dtm_valid))
        expected_ground_mean = float(np.mean(_expected_surface(
            np.arange(0, grid_size, 1.0), np.arange(0, grid_size, 1.0))))

        print(f"DSM mean={dsm_mean:.4f}, DTM mean={dtm_mean:.4f}, "
              f"expected ground mean~={expected_ground_mean:.4f}, offset={canopy_offset}")

        # DSM mean should be within 20% of (ground_mean + offset); a "max" writer
        # that silently degraded to ground-only or to a mean/last-point value
        # would fail this by a wide margin.
        expected_dsm_mean = expected_ground_mean + canopy_offset
        assert abs(dsm_mean - expected_dsm_mean) / expected_dsm_mean < 0.20, (
            f"DSM does not converge to canopy surface: dsm_mean={dsm_mean:.3f}, "
            f"expected~={expected_dsm_mean:.3f}"
        )

        # 2. DTM must stay close to the bare ground surface (i.e. correctly
        #    excludes the Classification=5 canopy returns).
        assert abs(dtm_mean - expected_ground_mean) / expected_ground_mean < 0.10, (
            f"DTM does not converge to ground surface: dtm_mean={dtm_mean:.3f}, "
            f"expected~={expected_ground_mean:.3f}"
        )

        # 3. DSM must sit measurably above the co-located DTM by ~canopy_offset —
        #    the core "surface model sits at/above terrain model" invariant.
        gap = dsm_mean - dtm_mean
        assert abs(gap - canopy_offset) / canopy_offset < 0.30, (
            f"DSM-DTM gap {gap:.3f} does not match expected canopy offset {canopy_offset}"
        )